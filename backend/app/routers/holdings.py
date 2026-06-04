import uuid
import logging
from decimal import Decimal
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.database import get_db
from app.models.group import BuyLot, Label, SellLotAllocation, SourceGroup, TransactionLabel
from app.models.holding import Holding, PrincipalFlow, Transaction, TransactionType
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.holding import (
    BuyLotOut,
    HoldingCreateIn, HoldingDetailOut, HoldingOut, HoldingUpdateIn,
    SellLotAllocationOut,
    SnapshotOut,
    TransactionClassificationIn,
    TransactionIn,
    TransactionOut,
    ReviewedSellRepairIn,
)
from app.services import stock_fetcher
from app.services.lot_accounting import (
    SellAllocationInput,
    Transaction as AccountingTransaction,
    replay,
)
from app.services.price_cache import get_price
from app.services.snapshot_service import backfill_holding_snapshots, rebuild_holding_snapshots

router = APIRouter(prefix="/api/holdings", tags=["holdings"])
logger = logging.getLogger(__name__)
ZERO = Decimal(0)


def _recalculate_holding(
    holding: Holding,
    transactions: list[Transaction] | None = None,
) -> None:
    """Recompute the remaining position using the moving-average method."""
    quantity = Decimal(0)
    avg_price = Decimal(0)
    for tx in sorted(transactions if transactions is not None else holding.transactions, key=_transaction_sort_key):
        if tx.type == TransactionType.BUY:
            total_cost = quantity * avg_price + tx.quantity * tx.price
            quantity += tx.quantity
            avg_price = total_cost / quantity
        elif tx.type == TransactionType.SELL:
            if tx.quantity > quantity:
                raise ValueError("Sell quantity exceeds available holding quantity")
            quantity -= tx.quantity
            if quantity == 0:
                avg_price = Decimal(0)
    holding.quantity = quantity
    holding.avg_price = avg_price


def _transaction_sort_key(transaction: Transaction) -> tuple[date, str, str]:
    created_at = transaction.created_at if isinstance(transaction.created_at, datetime) else None
    transaction_id = transaction.id if isinstance(transaction.id, uuid.UUID) else None
    return (
        transaction.transaction_date,
        created_at.isoformat() if created_at else "9999-12-31T23:59:59",
        str(transaction_id) if transaction_id else "",
    )


def _holding_load_options():
    return (
        selectinload(Holding.transactions).selectinload(Transaction.buy_lot),
        selectinload(Holding.transactions).selectinload(Transaction.sell_allocations),
        selectinload(Holding.transactions).selectinload(Transaction.transaction_labels),
        selectinload(Holding.buy_lots),
    )


async def _get_owned_holding(
    db: AsyncSession,
    holding_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    lock: bool = False,
) -> Holding:
    query = (
        select(Holding)
        .where(Holding.id == holding_id)
        .where(Holding.user_id == user_id)
        .options(*_holding_load_options())
    )
    if lock:
        query = query.with_for_update()
    result = await db.execute(query)
    holding = result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    return holding


async def _validate_source_group_id(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_group_id: uuid.UUID | None,
) -> None:
    if source_group_id is None:
        return
    result = await db.execute(
        select(SourceGroup.id)
        .where(SourceGroup.id == source_group_id)
        .where(SourceGroup.user_id == user_id)
    )
    if set(result.scalars().all()) != {source_group_id}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source group not found")


async def _validate_label_ids(
    db: AsyncSession,
    user_id: uuid.UUID,
    label_ids: list[uuid.UUID],
) -> None:
    if not label_ids:
        return
    result = await db.execute(
        select(Label.id)
        .where(Label.id.in_(label_ids))
        .where(Label.user_id == user_id)
    )
    if set(result.scalars().all()) != set(label_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")


async def _lock_owned_buy_lots(
    db: AsyncSession,
    user_id: uuid.UUID,
    holding_id: uuid.UUID,
    buy_lot_ids: list[uuid.UUID],
) -> None:
    if not buy_lot_ids:
        return
    result = await db.execute(
        select(BuyLot.id)
        .where(BuyLot.id.in_(buy_lot_ids))
        .where(BuyLot.user_id == user_id)
        .where(BuyLot.holding_id == holding_id)
        .with_for_update()
    )
    if set(result.scalars().all()) != set(buy_lot_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buy lot not found")


def _transaction_label_ids(transaction: Transaction) -> list[uuid.UUID]:
    return sorted(
        (transaction_label.label_id for transaction_label in transaction.transaction_labels),
        key=str,
    )


def _buy_lot_to_out(lot: BuyLot) -> BuyLotOut:
    return BuyLotOut(
        id=lot.id,
        transaction_id=lot.transaction_id,
        source_group_id=lot.source_group_id,
        label_ids=_transaction_label_ids(lot.transaction),
        original_quantity=lot.original_quantity,
        remaining_quantity=lot.remaining_quantity,
        unit_price=lot.unit_price,
        transaction_date=lot.transaction.transaction_date,
    )


def _transaction_to_out(transaction: Transaction) -> TransactionOut:
    return TransactionOut(
        id=transaction.id,
        type=transaction.type,
        quantity=transaction.quantity,
        price=transaction.price,
        transaction_date=transaction.transaction_date,
        principal_flow=_transaction_principal_flow(transaction),
        created_at=transaction.created_at,
        source_group_id=transaction.source_group_id,
        label_ids=_transaction_label_ids(transaction),
        requires_review=bool(transaction.requires_review),
        buy_lot=_buy_lot_to_out(transaction.buy_lot) if transaction.buy_lot else None,
        sell_allocations=[
            SellLotAllocationOut(
                buy_lot_id=allocation.buy_lot_id,
                quantity=allocation.quantity,
            )
            for allocation in sorted(transaction.sell_allocations, key=lambda item: str(item.buy_lot_id))
        ],
    )


def _to_accounting_transaction(holding: Holding, transaction: Transaction) -> AccountingTransaction:
    return AccountingTransaction(
        id=transaction.id,
        holding_id=holding.id,
        ticker=holding.ticker,
        currency=holding.currency.value,
        type=transaction.type,
        quantity=transaction.quantity,
        price=transaction.price,
        transaction_date=transaction.transaction_date,
        created_at=transaction.created_at or datetime.max.replace(tzinfo=timezone.utc),
        principal_flow=_transaction_principal_flow(transaction).value,
        source_group_id=transaction.source_group_id,
        lot_id=transaction.buy_lot.id if transaction.buy_lot else None,
        label_ids=frozenset(_transaction_label_ids(transaction)),
        allocations=tuple(
            SellAllocationInput(
                buy_lot_id=allocation.buy_lot_id,
                quantity=allocation.quantity,
            )
            for allocation in transaction.sell_allocations
        ),
        requires_review=bool(transaction.requires_review),
    )


def _transaction_principal_flow(transaction: Transaction) -> PrincipalFlow:
    flow = getattr(transaction, "principal_flow", None)
    if isinstance(flow, PrincipalFlow):
        return flow
    if isinstance(flow, str):
        return PrincipalFlow(flow)
    return PrincipalFlow.DEPOSIT if transaction.type == TransactionType.BUY else PrincipalFlow.REINVEST


def _ensure_active_holding(holding: Holding) -> None:
    if not holding.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inactive holding does not support lot accounting operations",
        )


def _ensure_lot_accounting_ready(
    holding: Holding,
    transactions: list[Transaction] | None = None,
):
    replay_result = replay(
        [
            _to_accounting_transaction(holding, transaction)
            for transaction in (transactions if transactions is not None else holding.transactions)
        ]
    )
    if replay_result.accounting_status == "requires_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lot accounting requires review",
        )
    return replay_result


def _replay_and_update_lots(
    holding: Holding,
    transactions: list[Transaction] | None = None,
) -> None:
    replay_result = _ensure_lot_accounting_ready(holding, transactions)
    _update_lot_mirrors(holding, replay_result)


def _update_lot_mirrors(holding: Holding, replay_result) -> None:
    lots_by_id = {lot.id: lot for lot in holding.buy_lots}
    for lot_id, lot_state in replay_result.all_lots.items():
        lot = lots_by_id.get(lot_id)
        if lot is not None:
            lot.remaining_quantity = lot_state.remaining_quantity


def _oldest_reviewed_sell(holding: Holding) -> Transaction | None:
    return next(
        (
            transaction
            for transaction in sorted(holding.transactions, key=_transaction_sort_key)
            if transaction.type == TransactionType.SELL and transaction.requires_review
        ),
        None,
    )


def _get_reviewed_sell(holding: Holding, tx_id: uuid.UUID) -> Transaction:
    transaction = next(
        (
            item
            for item in holding.transactions
            if item.id == tx_id and item.type == TransactionType.SELL and item.requires_review
        ),
        None,
    )
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reviewed sell not found")
    oldest = _oldest_reviewed_sell(holding)
    if oldest is None or oldest.id != transaction.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resolve earlier reviewed sells first",
        )
    return transaction


def _validate_lot_scope(
    scope_kind: Literal["source", "unclassified"],
    scope_id: uuid.UUID | None,
) -> None:
    if scope_kind == "source" and scope_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source scope requires scope_id",
        )
    if scope_kind == "unclassified" and scope_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unclassified scope does not accept scope_id",
        )


async def _replace_transaction_labels(
    db: AsyncSession,
    transaction: Transaction,
    label_ids: list[uuid.UUID],
) -> None:
    existing_by_label_id = {
        transaction_label.label_id: transaction_label
        for transaction_label in transaction.transaction_labels
    }
    requested_label_ids = set(label_ids)
    for transaction_label in list(transaction.transaction_labels):
        if transaction_label.label_id not in requested_label_ids:
            await db.delete(transaction_label)
    transaction_labels = [
        existing_by_label_id.get(label_id)
        or TransactionLabel(transaction_id=transaction.id, label_id=label_id)
        for label_id in label_ids
    ]
    set_committed_value(transaction, "transaction_labels", transaction_labels)
    for transaction_label in transaction_labels:
        if transaction_label.label_id not in existing_by_label_id:
            db.add(transaction_label)


async def _rebuild_snapshots_after_mutation(
    db: AsyncSession,
    holding: Holding,
    *,
    start: date | None,
    invalidate_start: date | None = None,
) -> None:
    try:
        kwargs = {"start": start}
        if invalidate_start is not None and invalidate_start != start:
            kwargs["invalidate_start"] = invalidate_start
        await rebuild_holding_snapshots(db, holding, **kwargs)
    except Exception:
        logger.exception(
            "Failed to rebuild snapshots for holding_id=%s from %s",
            holding.id,
            invalidate_start or start,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Price history rebuild failed; retry the transaction",
        )


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

    await _validate_source_group_id(db, current_user.id, body.source_group_id)
    await _validate_label_ids(db, current_user.id, body.label_ids)

    market = stock_fetcher.detect_market(body.ticker)
    currency = stock_fetcher.detect_currency(market)
    try:
        price_result = stock_fetcher.get_current_price(body.ticker)
        name = price_result.name
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ticker could not be verified",
        )

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
        is_active=True,
    )
    db.add(holding)
    await db.flush()

    tx = Transaction(
        holding_id=holding.id,
        user_id=current_user.id,
        source_group_id=body.source_group_id,
        type=TransactionType.BUY,
        quantity=body.quantity,
        price=body.price,
        transaction_date=body.transaction_date,
        principal_flow=body.principal_flow,
    )
    holding.transactions.append(tx)
    db.add(tx)
    await db.flush()

    lot = BuyLot(
        transaction_id=tx.id,
        holding_id=holding.id,
        transaction=tx,
        holding=holding,
        user_id=current_user.id,
        source_group_id=body.source_group_id,
        original_quantity=body.quantity,
        remaining_quantity=body.quantity,
        unit_price=body.price,
    )
    db.add(lot)
    await _replace_transaction_labels(db, tx, body.label_ids)
    await db.flush()

    try:
        await backfill_holding_snapshots(db, holding)
    except Exception:
        logger.exception("Failed to backfill snapshots for holding_id=%s", holding.id)

    await db.refresh(holding, ["holding_tags", "snapshots"])
    out = HoldingDetailOut(
        **( await _enrich_with_price(holding, None)).model_dump(),
        transactions=[_transaction_to_out(tx)],
        snapshots=[SnapshotOut.model_validate(s) for s in sorted(holding.snapshots, key=lambda x: x.snapshot_date)],
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
            *_holding_load_options(),
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
        transactions=[_transaction_to_out(t) for t in holding.transactions],
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
    holding = await _get_owned_holding(db, holding_id, current_user.id, lock=True)
    _ensure_active_holding(holding)
    _ensure_lot_accounting_ready(holding)
    result = await db.execute(
        select(BuyLot.id)
        .where(BuyLot.holding_id == holding.id)
        .where(BuyLot.user_id == current_user.id)
        .where(BuyLot.remaining_quantity > ZERO)
        .limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Holding with remaining lots cannot be deleted",
        )
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
    holding = await _get_owned_holding(db, holding_id, current_user.id)
    return [_transaction_to_out(transaction) for transaction in holding.transactions]


@router.post("/{holding_id}/transactions", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def add_transaction(
    holding_id: uuid.UUID,
    body: TransactionIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    holding = await _get_owned_holding(db, holding_id, current_user.id, lock=True)
    _ensure_active_holding(holding)
    _ensure_lot_accounting_ready(holding)
    await _validate_source_group_id(db, current_user.id, body.source_group_id)
    await _validate_label_ids(db, current_user.id, body.label_ids)
    await _lock_owned_buy_lots(
        db,
        current_user.id,
        holding.id,
        [allocation.buy_lot_id for allocation in body.sell_allocations],
    )

    tx = Transaction(
        holding_id=holding.id,
        user_id=current_user.id,
        source_group_id=body.source_group_id,
        type=body.type,
        quantity=body.quantity,
        price=body.price,
        transaction_date=body.transaction_date,
        principal_flow=body.principal_flow,
        requires_review=False,
        transaction_labels=[],
        sell_allocations=[],
    )
    holding.transactions.append(tx)
    db.add(tx)
    await db.flush()

    if body.type == TransactionType.BUY:
        lot = BuyLot(
            transaction_id=tx.id,
            holding_id=holding.id,
            transaction=tx,
            holding=holding,
            user_id=current_user.id,
            source_group_id=body.source_group_id,
            original_quantity=body.quantity,
            remaining_quantity=body.quantity,
            unit_price=body.price,
        )
        db.add(lot)
    else:
        for allocation_in in body.sell_allocations:
            allocation = SellLotAllocation(
                sell_transaction_id=tx.id,
                sell_transaction=tx,
                buy_lot_id=allocation_in.buy_lot_id,
                quantity=allocation_in.quantity,
            )
            db.add(allocation)

    await _replace_transaction_labels(db, tx, body.label_ids)
    await db.flush()
    try:
        _replay_and_update_lots(holding)
        _recalculate_holding(holding)
    except ValueError as exc:
        holding.transactions.remove(tx)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if body.type == TransactionType.BUY and holding.first_buy_date > body.transaction_date:
        holding.first_buy_date = body.transaction_date

    await _rebuild_snapshots_after_mutation(db, holding, start=body.transaction_date)
    return _transaction_to_out(tx)


@router.get("/{holding_id}/lots", response_model=list[BuyLotOut])
async def list_available_lots(
    holding_id: uuid.UUID,
    scope_kind: Literal["source", "unclassified"],
    scope_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    holding = await _get_owned_holding(db, holding_id, current_user.id)
    _ensure_active_holding(holding)
    _ensure_lot_accounting_ready(holding)
    _validate_lot_scope(scope_kind, scope_id)
    await _validate_source_group_id(db, current_user.id, scope_id)

    query = (
        select(BuyLot)
        .where(BuyLot.holding_id == holding_id)
        .where(BuyLot.user_id == current_user.id)
        .where(BuyLot.remaining_quantity > ZERO)
        .options(selectinload(BuyLot.transaction).selectinload(Transaction.transaction_labels))
        .order_by(BuyLot.created_at, BuyLot.id)
    )
    if scope_kind == "source":
        query = query.where(BuyLot.source_group_id == scope_id)
    else:
        query = query.where(BuyLot.source_group_id.is_(None))
    result = await db.execute(query)
    return [_buy_lot_to_out(lot) for lot in result.scalars().all()]


@router.get("/{holding_id}/transactions/{tx_id}/review-lots", response_model=list[BuyLotOut])
async def list_review_lots(
    holding_id: uuid.UUID,
    tx_id: uuid.UUID,
    scope_kind: Literal["source", "unclassified"],
    scope_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    holding = await _get_owned_holding(db, holding_id, current_user.id)
    _ensure_active_holding(holding)
    transaction = _get_reviewed_sell(holding, tx_id)
    _validate_lot_scope(scope_kind, scope_id)
    await _validate_source_group_id(db, current_user.id, scope_id)

    ordered_transactions = sorted(holding.transactions, key=_transaction_sort_key)
    transaction_index = next(
        index for index, item in enumerate(ordered_transactions) if item.id == transaction.id
    )
    replay_result = replay(
        [
            _to_accounting_transaction(holding, item)
            for item in ordered_transactions[:transaction_index]
        ]
    )
    lots_by_id = {lot.id: lot for lot in holding.buy_lots}
    lots = []
    for lot_id, lot_state in replay_result.all_lots.items():
        if lot_state.remaining_quantity <= ZERO:
            continue
        if scope_kind == "source" and lot_state.source_group_id != scope_id:
            continue
        if scope_kind == "unclassified" and lot_state.source_group_id is not None:
            continue
        lot = lots_by_id.get(lot_id)
        if lot is not None:
            lots.append(
                _buy_lot_to_out(lot).model_copy(
                    update={"remaining_quantity": lot_state.remaining_quantity}
                )
            )
    return sorted(lots, key=lambda lot: (lot.transaction_date, str(lot.id)))


@router.patch("/{holding_id}/transactions/{tx_id}/review", response_model=TransactionOut)
async def repair_reviewed_sell(
    holding_id: uuid.UUID,
    tx_id: uuid.UUID,
    body: ReviewedSellRepairIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    holding = await _get_owned_holding(db, holding_id, current_user.id, lock=True)
    _ensure_active_holding(holding)
    transaction = _get_reviewed_sell(holding, tx_id)
    await _validate_source_group_id(db, current_user.id, body.source_group_id)
    await _validate_label_ids(db, current_user.id, body.label_ids)
    await _lock_owned_buy_lots(
        db,
        current_user.id,
        holding.id,
        [allocation.buy_lot_id for allocation in body.sell_allocations],
    )

    allocations = [
        SellLotAllocation(
            sell_transaction_id=transaction.id,
            sell_transaction=transaction,
            buy_lot_id=allocation.buy_lot_id,
            quantity=allocation.quantity,
        )
        for allocation in body.sell_allocations
    ]
    original_source_group_id = transaction.source_group_id
    transaction.source_group_id = body.source_group_id
    transaction.requires_review = False
    transaction.sell_allocations = allocations
    try:
        replay_result = replay(
            [
                _to_accounting_transaction(holding, item)
                for item in holding.transactions
            ]
        )
    except ValueError as exc:
        transaction.source_group_id = original_source_group_id
        transaction.requires_review = True
        transaction.sell_allocations = []
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    for allocation in allocations:
        db.add(allocation)
    await _replace_transaction_labels(db, transaction, body.label_ids)
    await db.flush()
    _update_lot_mirrors(holding, replay_result)
    _recalculate_holding(holding)
    await _rebuild_snapshots_after_mutation(db, holding, start=transaction.transaction_date)
    return _transaction_to_out(transaction)


@router.patch("/{holding_id}/transactions/{tx_id}/classification", response_model=TransactionOut)
async def update_transaction_classification(
    holding_id: uuid.UUID,
    tx_id: uuid.UUID,
    body: TransactionClassificationIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    holding = await _get_owned_holding(db, holding_id, current_user.id, lock=True)
    _ensure_active_holding(holding)
    _ensure_lot_accounting_ready(holding)
    result = await db.execute(
        select(Transaction)
        .where(Transaction.id == tx_id)
        .where(Transaction.holding_id == holding.id)
        .where(Transaction.user_id == current_user.id)
    )
    transaction = result.scalar_one_or_none()
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    await _validate_source_group_id(db, current_user.id, body.source_group_id)
    await _validate_label_ids(db, current_user.id, body.label_ids)

    original_source_group_id = transaction.source_group_id
    original_lot_source_group_id = transaction.buy_lot.source_group_id if transaction.buy_lot else None
    transaction.source_group_id = body.source_group_id
    if transaction.buy_lot is not None:
        transaction.buy_lot.source_group_id = body.source_group_id
    try:
        _replay_and_update_lots(holding)
    except ValueError as exc:
        transaction.source_group_id = original_source_group_id
        if transaction.buy_lot is not None:
            transaction.buy_lot.source_group_id = original_lot_source_group_id
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    await _replace_transaction_labels(db, transaction, body.label_ids)
    await db.flush()
    return _transaction_to_out(transaction)


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
    holding = await _get_owned_holding(db, holding_id, current_user.id, lock=True)
    _ensure_active_holding(holding)
    _ensure_lot_accounting_ready(holding)

    remaining_transactions = [item for item in holding.transactions if item.id != tx_id]
    try:
        _replay_and_update_lots(holding, remaining_transactions)
        _recalculate_holding(holding, remaining_transactions)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    buy_dates = [
        item.transaction_date
        for item in remaining_transactions
        if item.type == TransactionType.BUY
    ]
    if buy_dates:
        holding.first_buy_date = min(buy_dates)
        regenerate_start = max(tx.transaction_date, holding.first_buy_date)
    else:
        regenerate_start = None
    await db.delete(tx)
    holding.transactions.remove(tx)
    await _rebuild_snapshots_after_mutation(
        db,
        holding,
        start=regenerate_start,
        invalidate_start=tx.transaction_date,
    )
