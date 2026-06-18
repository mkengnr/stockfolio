import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding, Transaction, TransactionType
from app.models.snapshot import DailySnapshot
from app.services import stock_fetcher
from app.services.stock_fetcher import OHLCBar


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
