import uuid
from decimal import Decimal
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.holding import Holding, Transaction, TransactionType
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.holding import (
    HoldingCreateIn, HoldingDetailOut, HoldingOut, HoldingUpdateIn,
    TransactionIn, TransactionOut, SnapshotOut,
)
from app.services import stock_fetcher
from app.services.price_cache import get_price

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


def _recalculate_holding(holding: Holding) -> None:
    """Recompute avg_price and net quantity from transactions.

    avg_price is the weighted average of all BUY transactions only —
    it does not change when shares are sold (FIFO cost basis).
    net_qty = sum(BUY) - sum(SELL).
    """
    net_qty = Decimal(0)
    total_buy_qty = Decimal(0)
    total_buy_cost = Decimal(0)
    for tx in holding.transactions:
        if tx.type == TransactionType.BUY:
            net_qty += tx.quantity
            total_buy_qty += tx.quantity
            total_buy_cost += tx.quantity * tx.price
        elif tx.type == TransactionType.SELL:
            net_qty -= tx.quantity
    holding.quantity = net_qty
    holding.avg_price = (total_buy_cost / total_buy_qty) if total_buy_qty > 0 else Decimal(0)


async def _enrich_with_price(holding: Holding, current_price: Decimal | None) -> HoldingOut:
    cost_basis = holding.quantity * holding.avg_price
    current_value = holding.quantity * current_price if current_price else None
    profit_loss = (current_value - cost_basis) if current_value is not None else None
    profit_loss_pct = (profit_loss / cost_basis * 100) if (profit_loss is not None and cost_basis > 0) else None

    return HoldingOut(
        id=holding.id,
        ticker=holding.ticker,
        market=holding.market,
        name=holding.name,
        quantity=holding.quantity,
        avg_price=holding.avg_price,
        currency=holding.currency,
        first_buy_date=holding.first_buy_date,
        notes=holding.notes,
        is_active=holding.is_active,
        created_at=holding.created_at,
        current_price=current_price,
        current_value=current_value,
        profit_loss=profit_loss,
        profit_loss_pct=profit_loss_pct,
        cost_basis=cost_basis,
    )


@router.get("", response_model=list[HoldingOut])
async def list_holdings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Holding)
        .where(Holding.user_id == current_user.id)
        .where(Holding.is_active == True)
        .options(selectinload(Holding.transactions))
    )
    holdings = result.scalars().all()

    enriched = []
    for h in holdings:
        try:
            price_result = await get_price(h.ticker)
            current_price = price_result.price
        except Exception:
            current_price = None
        enriched.append(await _enrich_with_price(h, current_price))
    return enriched


@router.post("", response_model=HoldingDetailOut, status_code=status.HTTP_201_CREATED)
async def create_holding(
    body: HoldingCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check duplicate active holding
    existing = await db.execute(
        select(Holding)
        .where(Holding.user_id == current_user.id)
        .where(Holding.ticker == body.ticker)
        .where(Holding.is_active == True)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active holding already exists for this ticker")

    market = stock_fetcher.detect_market(body.ticker)
    currency = stock_fetcher.detect_currency(market)
    try:
        price_result = stock_fetcher.get_current_price(body.ticker)
        name = price_result.name
    except Exception:
        name = body.ticker

    holding = Holding(
        user_id=current_user.id,
        ticker=body.ticker,
        market=market,
        name=name,
        quantity=body.quantity,
        avg_price=body.price,
        currency=currency,
        first_buy_date=body.transaction_date,
        notes=body.notes,
    )
    db.add(holding)
    await db.flush()

    tx = Transaction(
        holding_id=holding.id,
        user_id=current_user.id,
        type=TransactionType.BUY,
        quantity=body.quantity,
        price=body.price,
        transaction_date=body.transaction_date,
    )
    db.add(tx)
    await db.flush()

    await db.refresh(holding, ["transactions", "holding_tags", "snapshots"])
    out = HoldingDetailOut(
        **( await _enrich_with_price(holding, None)).model_dump(),
        transactions=[TransactionOut.model_validate(tx)],
        snapshots=[],
        tags=[],
    )
    return out


@router.get("/{holding_id}", response_model=HoldingDetailOut)
async def get_holding(
    holding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id)
        .where(Holding.user_id == current_user.id)
        .options(
            selectinload(Holding.transactions),
            selectinload(Holding.holding_tags),
            selectinload(Holding.snapshots),
        )
    )
    holding = result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")

    try:
        price_result = await get_price(holding.ticker)
        current_price = price_result.price
    except Exception:
        current_price = None

    base = await _enrich_with_price(holding, current_price)
    return HoldingDetailOut(
        **base.model_dump(),
        transactions=[TransactionOut.model_validate(t) for t in holding.transactions],
        snapshots=[SnapshotOut.model_validate(s) for s in sorted(holding.snapshots, key=lambda x: x.snapshot_date)],
        tags=[ht.tag_id for ht in holding.holding_tags],
    )


@router.put("/{holding_id}", response_model=HoldingOut)
async def update_holding(
    holding_id: uuid.UUID,
    body: HoldingUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id)
        .where(Holding.user_id == current_user.id)
    )
    holding = result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")

    if body.notes is not None:
        holding.notes = body.notes
    if body.name is not None:
        holding.name = body.name
    return await _enrich_with_price(holding, None)


@router.delete("/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holding(
    holding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id)
        .where(Holding.user_id == current_user.id)
    )
    holding = result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    holding.is_active = False


# ---------------------------------------------------------------------------
# Transactions sub-resource
# ---------------------------------------------------------------------------

@router.get("/{holding_id}/transactions", response_model=list[TransactionOut])
async def list_transactions(
    holding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id)
        .where(Holding.user_id == current_user.id)
        .options(selectinload(Holding.transactions))
    )
    holding = result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    return [TransactionOut.model_validate(t) for t in holding.transactions]


@router.post("/{holding_id}/transactions", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def add_transaction(
    holding_id: uuid.UUID,
    body: TransactionIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id)
        .where(Holding.user_id == current_user.id)
        .options(selectinload(Holding.transactions))
    )
    holding = result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")

    tx = Transaction(
        holding_id=holding.id,
        user_id=current_user.id,
        type=body.type,
        quantity=body.quantity,
        price=body.price,
        transaction_date=body.transaction_date,
    )
    db.add(tx)
    await db.flush()

    holding.transactions.append(tx)
    _recalculate_holding(holding)

    if holding.first_buy_date > body.transaction_date:
        holding.first_buy_date = body.transaction_date

    return TransactionOut.model_validate(tx)


@router.delete("/{holding_id}/transactions/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    holding_id: uuid.UUID,
    tx_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction)
        .where(Transaction.id == tx_id)
        .where(Transaction.holding_id == holding_id)
        .where(Transaction.user_id == current_user.id)
    )
    tx = result.scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    await db.delete(tx)

    # Recalculate holding
    holding_result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id)
        .options(selectinload(Holding.transactions))
    )
    holding = holding_result.scalar_one_or_none()
    if holding:
        _recalculate_holding(holding)
