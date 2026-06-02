import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
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


def _transaction_sort_key(transaction: Transaction) -> tuple[date, str]:
    created_at = getattr(transaction, "created_at", None)
    return (
        transaction.transaction_date,
        created_at.isoformat() if created_at else "9999-12-31T23:59:59",
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
