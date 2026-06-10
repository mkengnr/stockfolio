import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.group import Label, SourceGroup, TransactionLabel
from app.models.holding import Holding, PrincipalFlow, Transaction, TransactionType
from app.models.user import User
from app.routers.deps import get_current_user
from app.routers.holdings import (
    _ensure_active_holding,
    _ensure_buy_lot_not_allocated,
    _ensure_lot_accounting_ready,
    _get_owned_holding,
    _recalculate_holding,
    _replace_transaction_labels,
    _replay_and_update_lots,
    _transaction_principal_flow,
)
from app.schemas.transaction import (
    TransactionListItemOut,
    TransactionListOut,
    TransactionUpdateIn,
)
from app.services.snapshot_service import rebuild_holding_snapshots

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
logger = logging.getLogger(__name__)


def _label_metadata(transaction: Transaction) -> tuple[list[uuid.UUID], list[str]]:
    transaction_labels = sorted(
        transaction.transaction_labels,
        key=lambda item: str(item.label_id),
    )
    return (
        [item.label_id for item in transaction_labels],
        [item.label.name for item in transaction_labels if getattr(item, "label", None) is not None],
    )


def _transaction_to_list_item(transaction: Transaction) -> TransactionListItemOut:
    label_ids, label_names = _label_metadata(transaction)
    return TransactionListItemOut(
        id=transaction.id,
        holding_id=transaction.holding_id,
        ticker=transaction.holding.ticker,
        holding_name=transaction.holding.name,
        currency=transaction.holding.currency,
        type=transaction.type,
        transaction_date=transaction.transaction_date,
        quantity=transaction.quantity,
        price=transaction.price,
        amount=transaction.quantity * transaction.price,
        principal_flow=_transaction_principal_flow(transaction),
        source_group_id=transaction.source_group_id,
        source_group_name=transaction.source_group.name if transaction.source_group else None,
        label_ids=label_ids,
        label_names=label_names,
        requires_review=bool(transaction.requires_review),
        created_at=transaction.created_at,
    )


def _source_group_by_id(source_groups: list[SourceGroup]) -> dict[uuid.UUID, SourceGroup]:
    return {source_group.id: source_group for source_group in source_groups}


def _label_by_id(labels: list[Label]) -> dict[uuid.UUID, Label]:
    return {label.id: label for label in labels}


def _find_transaction_on_locked_holding(
    holding: Holding,
    transaction_id: uuid.UUID,
) -> Transaction:
    transaction = next(
        (item for item in holding.transactions if item.id == transaction_id),
        None,
    )
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


async def _get_owned_transaction(
    db: AsyncSession,
    transaction_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Transaction:
    result = await db.execute(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .where(Transaction.user_id == user_id)
        .options(
            selectinload(Transaction.holding),
            selectinload(Transaction.source_group),
            selectinload(Transaction.transaction_labels).selectinload(TransactionLabel.label),
            selectinload(Transaction.buy_lot),
            selectinload(Transaction.sell_allocations),
        )
    )
    transaction = result.scalar_one_or_none()
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


async def _get_owned_transaction_holding_id(
    db: AsyncSession,
    transaction_id: uuid.UUID,
    user_id: uuid.UUID,
) -> uuid.UUID:
    result = await db.execute(
        select(Transaction.holding_id)
        .join(Holding, Holding.id == Transaction.holding_id)
        .where(Transaction.id == transaction_id)
        .where(Transaction.user_id == user_id)
        .where(Holding.user_id == user_id)
    )
    holding_id = result.scalar_one_or_none()
    if holding_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return holding_id


async def _load_owned_source_group(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_group_id: uuid.UUID | None,
) -> SourceGroup | None:
    if source_group_id is None:
        return None
    result = await db.execute(
        select(SourceGroup)
        .where(SourceGroup.id == source_group_id)
        .where(SourceGroup.user_id == user_id)
    )
    source_group = result.scalar_one_or_none()
    if source_group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source group not found")
    return source_group


async def _load_owned_source_groups(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_group_ids: list[uuid.UUID],
) -> list[SourceGroup]:
    if not source_group_ids:
        return []
    result = await db.execute(
        select(SourceGroup)
        .where(SourceGroup.id.in_(source_group_ids))
        .where(SourceGroup.user_id == user_id)
    )
    source_groups = result.scalars().all()
    if set(_source_group_by_id(source_groups)) != set(source_group_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source group not found")
    return source_groups


async def _load_owned_labels(
    db: AsyncSession,
    user_id: uuid.UUID,
    label_ids: list[uuid.UUID],
) -> list[Label]:
    if not label_ids:
        return []
    result = await db.execute(
        select(Label)
        .where(Label.id.in_(label_ids))
        .where(Label.user_id == user_id)
    )
    labels = result.scalars().all()
    labels_by_id = {label.id: label for label in labels}
    if set(labels_by_id) != set(label_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
    return [labels_by_id[label_id] for label_id in label_ids]


async def _hydrate_transaction_metadata(
    db: AsyncSession,
    user_id: uuid.UUID,
    transaction: Transaction,
) -> None:
    source_groups = await _load_owned_source_groups(
        db,
        user_id,
        [transaction.source_group_id] if transaction.source_group_id is not None else [],
    )
    source_groups_by_id = _source_group_by_id(source_groups)
    transaction.source_group = (
        source_groups_by_id.get(transaction.source_group_id)
        if transaction.source_group_id is not None
        else None
    )
    label_ids = [transaction_label.label_id for transaction_label in transaction.transaction_labels]
    labels = await _load_owned_labels(db, user_id, label_ids)
    labels_by_id = _label_by_id(labels)
    for transaction_label in transaction.transaction_labels:
        transaction_label.label = labels_by_id.get(transaction_label.label_id)


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


def _validate_principal_flow_for_type(
    transaction_type: TransactionType,
    principal_flow: PrincipalFlow,
) -> None:
    if transaction_type == TransactionType.BUY and principal_flow == PrincipalFlow.WITHDRAW:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="BUY transactions cannot withdraw principal",
        )
    if transaction_type == TransactionType.SELL and principal_flow == PrincipalFlow.DEPOSIT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="SELL transactions cannot deposit principal",
        )


def _refresh_first_buy_date(holding: Holding) -> None:
    buy_dates = [
        transaction.transaction_date
        for transaction in holding.transactions
        if transaction.type == TransactionType.BUY
    ]
    if buy_dates:
        holding.first_buy_date = min(buy_dates)


@router.get("", response_model=TransactionListOut)
async def list_transactions(
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(default=None),
    source_group_id: uuid.UUID | None = None,
    type: TransactionType | None = None,
    principal_flow: PrincipalFlow | None = None,
    requires_review: bool | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = [
        Transaction.user_id == current_user.id,
        Holding.user_id == current_user.id,
    ]
    if date_from is not None:
        filters.append(Transaction.transaction_date >= date_from)
    if date_to is not None:
        filters.append(Transaction.transaction_date <= date_to)
    if q:
        pattern = f"%{q.strip().lower()}%"
        filters.append(
            or_(
                func.lower(Holding.ticker).like(pattern),
                func.lower(Holding.name).like(pattern),
            )
        )
    if source_group_id is not None:
        filters.append(Transaction.source_group_id == source_group_id)
    if type is not None:
        filters.append(Transaction.type == type)
    if principal_flow is not None:
        filters.append(Transaction.principal_flow == principal_flow)
    if requires_review is not None:
        filters.append(Transaction.requires_review == requires_review)

    count_result = await db.execute(
        select(func.count())
        .select_from(Transaction)
        .join(Holding, Holding.id == Transaction.holding_id)
        .where(*filters)
    )
    total = count_result.scalar_one()

    query = (
        select(Transaction)
        .join(Holding, Holding.id == Transaction.holding_id)
        .where(*filters)
        .options(
            selectinload(Transaction.holding),
            selectinload(Transaction.source_group),
            selectinload(Transaction.transaction_labels).selectinload(TransactionLabel.label),
        )
        .order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    return TransactionListOut(
        transactions=[_transaction_to_list_item(transaction) for transaction in result.scalars().all()],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{transaction_id}", response_model=TransactionListItemOut)
async def update_transaction(
    transaction_id: uuid.UUID,
    body: TransactionUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    holding_id = await _get_owned_transaction_holding_id(db, transaction_id, current_user.id)
    holding = await _get_owned_holding(db, holding_id, current_user.id, lock=True)
    transaction = _find_transaction_on_locked_holding(holding, transaction_id)
    _ensure_active_holding(holding)
    _ensure_lot_accounting_ready(holding)

    fields_set = body.model_fields_set
    if (
        transaction.type == TransactionType.SELL
        and "quantity" in fields_set
        and body.quantity != transaction.quantity
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SELL quantity cannot be changed from the transactions list",
        )
    if "principal_flow" in fields_set and body.principal_flow is not None:
        _validate_principal_flow_for_type(transaction.type, body.principal_flow)
    source_group: SourceGroup | None = None
    if "source_group_id" in fields_set:
        source_group = await _load_owned_source_group(db, current_user.id, body.source_group_id)
    labels: list[Label] | None = None
    if "label_ids" in fields_set and body.label_ids is not None:
        labels = await _load_owned_labels(db, current_user.id, body.label_ids)

    original_date = transaction.transaction_date
    original_values = {
        "transaction_date": transaction.transaction_date,
        "quantity": transaction.quantity,
        "price": transaction.price,
        "principal_flow": transaction.principal_flow,
        "source_group_id": transaction.source_group_id,
    }
    original_lot_values = None
    if transaction.buy_lot is not None:
        original_lot_values = {
            "original_quantity": transaction.buy_lot.original_quantity,
            "remaining_quantity": transaction.buy_lot.remaining_quantity,
            "unit_price": transaction.buy_lot.unit_price,
            "source_group_id": transaction.buy_lot.source_group_id,
        }

    if "transaction_date" in fields_set and body.transaction_date is not None:
        transaction.transaction_date = body.transaction_date
    if transaction.type == TransactionType.BUY and "quantity" in fields_set and body.quantity is not None:
        transaction.quantity = body.quantity
    if "price" in fields_set and body.price is not None:
        transaction.price = body.price
    if "principal_flow" in fields_set and body.principal_flow is not None:
        transaction.principal_flow = body.principal_flow
    if "source_group_id" in fields_set:
        transaction.source_group_id = body.source_group_id
        transaction.source_group = source_group

    if transaction.buy_lot is not None:
        transaction.buy_lot.original_quantity = transaction.quantity
        transaction.buy_lot.unit_price = transaction.price
        transaction.buy_lot.source_group_id = transaction.source_group_id

    try:
        _replay_and_update_lots(holding)
        _recalculate_holding(holding)
    except ValueError as exc:
        for field, value in original_values.items():
            setattr(transaction, field, value)
        if transaction.buy_lot is not None and original_lot_values is not None:
            for field, value in original_lot_values.items():
                setattr(transaction.buy_lot, field, value)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if "label_ids" in fields_set and body.label_ids is not None:
        await _replace_transaction_labels(db, transaction, body.label_ids)
    await _hydrate_transaction_metadata(db, current_user.id, transaction)
    if transaction.type == TransactionType.BUY:
        _refresh_first_buy_date(holding)
    await db.flush()

    rebuild_start = min(original_date, transaction.transaction_date)
    await _rebuild_snapshots_after_mutation(
        db,
        holding,
        start=rebuild_start,
        invalidate_start=original_date,
    )
    return _transaction_to_list_item(transaction)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    holding_id = await _get_owned_transaction_holding_id(db, transaction_id, current_user.id)
    holding = await _get_owned_holding(db, holding_id, current_user.id, lock=True)
    transaction = _find_transaction_on_locked_holding(holding, transaction_id)
    _ensure_active_holding(holding)
    _ensure_lot_accounting_ready(holding)
    _ensure_buy_lot_not_allocated(holding, transaction)

    remaining_transactions = [
        item for item in holding.transactions if item.id != transaction_id
    ]
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
        regenerate_start = max(transaction.transaction_date, holding.first_buy_date)
    else:
        regenerate_start = None
    await db.delete(transaction)
    holding.transactions.remove(transaction)
    await _rebuild_snapshots_after_mutation(
        db,
        holding,
        start=regenerate_start,
        invalidate_start=transaction.transaction_date,
    )
