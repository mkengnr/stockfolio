import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding, Market, Transaction, TransactionType
from app.models.snapshot import DailySnapshot
from app.services import stock_fetcher
from app.services.market_session import is_write_confirmed
from app.services.stock_fetcher import OHLCBar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SnapshotValue:
    snapshot_date: date
    close_price: Decimal
    total_value: Decimal


def _transaction_sort_key(transaction: Transaction) -> tuple[date, str, str]:
    created_at = getattr(transaction, "created_at", None)
    return (
        transaction.transaction_date,
        created_at.isoformat() if created_at else "9999-12-31T23:59:59",
        str(transaction.id),
    )


def _build_snapshot_values(
    transactions: Iterable[Transaction],
    bars: Iterable[OHLCBar],
) -> list[SnapshotValue]:
    """Calculate each trading day's value using the quantity held on that day."""
    sorted_transactions = sorted(transactions, key=_transaction_sort_key)
    quantity = Decimal(0)
    transaction_index = 0
    values = []

    for bar in sorted(bars, key=lambda item: item.date):
        # Price providers occasionally return NaN/Inf closes for some dates;
        # skip those bars rather than storing a non-finite, unservable snapshot.
        if not bar.close.is_finite() or bar.close <= 0:
            continue
        while (
            transaction_index < len(sorted_transactions)
            and sorted_transactions[transaction_index].transaction_date <= bar.date
        ):
            transaction = sorted_transactions[transaction_index]
            if transaction.type == TransactionType.BUY:
                quantity += transaction.quantity
            elif transaction.type == TransactionType.SELL:
                quantity -= transaction.quantity
                if quantity < 0:
                    raise ValueError("Sell quantity exceeds available holding quantity")
            transaction_index += 1

        values.append(
            SnapshotValue(
                snapshot_date=bar.date,
                close_price=bar.close,
                total_value=quantity * bar.close,
            )
        )

    return values


async def backfill_holding_snapshots(
    db: AsyncSession,
    holding: Holding,
    *,
    start: date | None = None,
    end: date | None = None,
) -> int:
    """Store missing trading-day snapshots from the first buy date through today."""
    start = start or holding.first_buy_date
    end = end or date.today()
    if start > end:
        return 0

    existing_result = await db.execute(
        select(DailySnapshot.snapshot_date)
        .where(DailySnapshot.holding_id == holding.id)
        .where(DailySnapshot.snapshot_date >= start)
        .where(DailySnapshot.snapshot_date <= end)
    )
    existing_dates = set(existing_result.scalars().all())
    bars = await asyncio.to_thread(stock_fetcher.get_price_history, holding.ticker, start, end)

    added = 0
    for value in _build_snapshot_values(holding.transactions, bars):
        if value.snapshot_date < start or value.snapshot_date > end:
            continue
        if value.snapshot_date in existing_dates:
            continue
        db.add(
            DailySnapshot(
                holding_id=holding.id,
                snapshot_date=value.snapshot_date,
                close_price=value.close_price,
                total_value=value.total_value,
            )
        )
        added += 1

    if added:
        await db.flush()
    return added


async def backfill_recent_comparison_snapshots(
    db: AsyncSession,
    holding: Holding,
    *,
    current_price_date: date,
) -> int:
    """Store missing recent trading-day snapshots before the current quote date."""
    end = current_price_date - timedelta(days=1)
    start = max(holding.first_buy_date, current_price_date - timedelta(days=8))
    return await backfill_holding_snapshots(db, holding, start=start, end=end)


async def rebuild_holding_snapshots(
    db: AsyncSession,
    holding: Holding,
    *,
    start: date | None,
    invalidate_start: date | None = None,
    end: date | None = None,
) -> int:
    """Rebuild derived values after a backdated transaction mutation."""
    invalidate_start = invalidate_start or start
    end = end or date.today()
    values = []
    if start is not None and start <= end:
        bars = await asyncio.to_thread(stock_fetcher.get_price_history, holding.ticker, start, end)
        values = _build_snapshot_values(holding.transactions, bars)

    # Delete from the earliest affected date so every date we are about to
    # re-insert (from `start`) is cleared first; otherwise a backdated-earlier
    # edit (start < invalidate_start) re-inserts existing rows and violates the
    # (holding_id, snapshot_date) unique constraint.
    delete_start = invalidate_start
    if start is not None and (delete_start is None or start < delete_start):
        delete_start = start
    if delete_start is not None:
        await db.execute(
            delete(DailySnapshot)
            .where(DailySnapshot.holding_id == holding.id)
            .where(DailySnapshot.snapshot_date >= delete_start)
        )

    for value in values:
        db.add(
            DailySnapshot(
                holding_id=holding.id,
                snapshot_date=value.snapshot_date,
                close_price=value.close_price,
                total_value=value.total_value,
            )
        )
    if values:
        await db.flush()
    return len(values)


def _quantity_on_date(holding, on: date) -> Decimal:
    """Return ledger quantity held as of `on` (inclusive)."""
    quantity = Decimal(0)
    for transaction in sorted(holding.transactions, key=_transaction_sort_key):
        if transaction.transaction_date > on:
            break
        if transaction.type == TransactionType.BUY:
            quantity += transaction.quantity
        elif transaction.type == TransactionType.SELL:
            quantity -= transaction.quantity
    return quantity


async def _upsert_snapshot(
    db,
    holding_id,
    snapshot_date: date,
    close_price: Decimal,
    total_value: Decimal,
) -> None:
    """Idempotent upsert: ON CONFLICT (holding_id, snapshot_date) DO UPDATE."""
    stmt = pg_insert(DailySnapshot).values(
        holding_id=holding_id,
        snapshot_date=snapshot_date,
        close_price=close_price,
        total_value=total_value,
    ).on_conflict_do_update(
        index_elements=["holding_id", "snapshot_date"],
        set_={
            "close_price": close_price,
            "total_value": total_value,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)


async def finalize_market_snapshots(
    db,
    holdings,
    now: datetime,
    *,
    get_price=stock_fetcher.get_current_price,
    close_overrides: dict[date, time] | None = None,
) -> dict[str, list]:
    """Confirm today's close for already-closed sessions; idempotent upsert at price_date.

    Returns confirmed (holding, PriceResult) pairs in results['confirmed'] so the caller
    can mirror them to Redis after commit.
    """
    results: dict[str, list] = {
        "written": [],
        "skipped_intraday": [],
        "failed": [],
        "confirmed": [],
    }
    for holding in holdings:
        try:
            pr = await asyncio.to_thread(get_price, holding.ticker)
        except Exception as exc:
            logger.warning("finalize price fetch failed ticker=%s: %r", holding.ticker, exc)
            results["failed"].append(holding.ticker)
            continue
        if pr.price is None or not pr.price.is_finite() or pr.price <= 0:
            logger.warning("finalize got unusable price ticker=%s", holding.ticker)
            results["failed"].append(holding.ticker)
            continue
        if not is_write_confirmed(pr.market, pr.price_date, now, close_overrides=close_overrides):
            results["skipped_intraday"].append(holding.ticker)
            continue
        quantity = _quantity_on_date(holding, pr.price_date)
        await _upsert_snapshot(db, holding.id, pr.price_date, pr.price, quantity * pr.price)
        results["written"].append((holding.ticker, pr.price_date))
        results["confirmed"].append((holding, pr))
    return results
