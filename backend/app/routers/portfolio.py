import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.holding import Currency, Holding, Transaction, TransactionType
from app.models.tag import HoldingTag, Tag
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.portfolio import PortfolioHistoryOut, PortfolioHistoryPoint

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@dataclass(frozen=True)
class HistoricalPosition:
    quantity: Decimal = Decimal(0)
    avg_cost: Decimal = Decimal(0)

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.avg_cost


def _apply_transaction(position: HistoricalPosition, transaction: Transaction) -> HistoricalPosition:
    """Apply one transaction using the moving-average cost method."""
    if transaction.quantity <= 0:
        raise ValueError("Transaction quantity must be positive")

    if transaction.type == TransactionType.BUY:
        quantity = position.quantity + transaction.quantity
        cost_basis = position.cost_basis + (transaction.quantity * transaction.price)
        return HistoricalPosition(quantity=quantity, avg_cost=cost_basis / quantity)

    if transaction.type == TransactionType.SELL:
        if transaction.quantity > position.quantity:
            raise ValueError("Sell quantity exceeds available quantity")
        quantity = position.quantity - transaction.quantity
        avg_cost = Decimal(0) if quantity == 0 else position.avg_cost
        return HistoricalPosition(quantity=quantity, avg_cost=avg_cost)

    raise ValueError(f"Unsupported transaction type: {transaction.type}")


def _transaction_sort_key(transaction: Transaction) -> tuple[date, datetime, str]:
    return (
        transaction.transaction_date,
        getattr(transaction, "created_at", datetime.min),
        str(getattr(transaction, "id", "")),
    )


def _build_portfolio_history(holdings: list[Holding]) -> PortfolioHistoryOut:
    """Aggregate close-price snapshots without mixing currencies."""
    totals: dict[Currency, dict[date, tuple[Decimal, Decimal]]] = {
        currency: {} for currency in Currency
    }

    for holding in holdings:
        transactions = sorted(holding.transactions, key=_transaction_sort_key)
        snapshots = sorted(holding.snapshots, key=lambda snapshot: snapshot.snapshot_date)
        position = HistoricalPosition()
        transaction_index = 0

        for snapshot in snapshots:
            while (
                transaction_index < len(transactions)
                and transactions[transaction_index].transaction_date <= snapshot.snapshot_date
            ):
                position = _apply_transaction(position, transactions[transaction_index])
                transaction_index += 1

            total_value, total_cost_basis = totals[holding.currency].get(
                snapshot.snapshot_date,
                (Decimal(0), Decimal(0)),
            )
            totals[holding.currency][snapshot.snapshot_date] = (
                total_value + (position.quantity * snapshot.close_price),
                total_cost_basis + position.cost_basis,
            )

        # Surface malformed transaction histories even when the invalid sell is
        # later than the most recent snapshot.
        while transaction_index < len(transactions):
            position = _apply_transaction(position, transactions[transaction_index])
            transaction_index += 1

    return PortfolioHistoryOut(
        series={
            currency: [
                PortfolioHistoryPoint(
                    snapshot_date=snapshot_date,
                    total_value=total_value,
                    total_cost_basis=total_cost_basis,
                )
                for snapshot_date, (total_value, total_cost_basis) in sorted(days.items())
            ]
            for currency, days in totals.items()
        }
    )


def _owned_tag_query(tag_id: uuid.UUID, user_id: uuid.UUID) -> Select[tuple[Tag]]:
    return select(Tag).where(Tag.id == tag_id).where(Tag.user_id == user_id)


def _holdings_query(user_id: uuid.UUID, tag_id: uuid.UUID | None) -> Select[tuple[Holding]]:
    query = (
        select(Holding)
        .where(Holding.user_id == user_id)
        .options(
            selectinload(Holding.transactions),
            selectinload(Holding.snapshots),
        )
    )
    if tag_id is not None:
        query = query.join(HoldingTag, HoldingTag.holding_id == Holding.id).where(
            HoldingTag.tag_id == tag_id
        )
    return query


@router.get("/history", response_model=PortfolioHistoryOut)
async def get_portfolio_history(
    tag_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if tag_id is not None:
        tag_result = await db.execute(_owned_tag_query(tag_id, current_user.id))
        if tag_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    result = await db.execute(_holdings_query(current_user.id, tag_id))
    return _build_portfolio_history(list(result.scalars().all()))
