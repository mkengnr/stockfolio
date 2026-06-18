import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.group import (
    BuyLot,
    Label,
    RollupGroup,
    RollupGroupMember,
    SourceGroup,
    TransactionLabel,
)
from app.models.holding import Transaction
from app.models.user import User
from app.routers.deps import get_current_user, get_current_user_optional
from app.routers.portfolio import (
    build_shared_portfolio_dashboard,
    resolve_portfolio_scope,
)
from app.schemas.group import (
    GroupMetadataUpdateIn,
    LabelCreateIn,
    LabelOut,
    LabelUpdateIn,
    RollupGroupCreateIn,
    RollupGroupOut,
    RollupGroupUpdateIn,
    ShareUpdateIn,
    SharedDashboardGroupOut,
    SharedDashboardHistoryOut,
    SharedDashboardHistoryRowOut,
    SharedDashboardHoldingGroupBadgeOut,
    SharedDashboardHoldingOut,
    SharedDashboardOut,
    SharedGroupOut,
    SourceGroupCreateIn,
    SourceGroupOut,
    SourceGroupUpdateIn,
)
from app.schemas.dashboard import DashboardResponse


router = APIRouter(prefix="/api/groups", tags=["groups"])
GroupKind = Literal["sources", "rollups", "labels"]
GroupEntity = SourceGroup | RollupGroup | Label
GroupOut = SourceGroupOut | RollupGroupOut | LabelOut

_GROUP_MODELS = {
    "sources": SourceGroup,
    "rollups": RollupGroup,
    "labels": Label,
}


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")


def _apply_metadata(entity: GroupEntity, body: GroupMetadataUpdateIn) -> None:
    for field in ("name", "color", "description", "share_description"):
        if field in body.model_fields_set:
            setattr(entity, field, getattr(body, field))


def _rollup_to_out(
    rollup: RollupGroup,
    source_group_ids: list[uuid.UUID] | None = None,
) -> RollupGroupOut:
    if source_group_ids is None:
        source_group_ids = [member.source_group_id for member in rollup.members]
    return RollupGroupOut(
        id=rollup.id,
        name=rollup.name,
        color=rollup.color,
        description=rollup.description,
        share_description=rollup.share_description,
        share_token=rollup.share_token,
        share_requires_auth=rollup.share_requires_auth,
        source_group_ids=sorted(source_group_ids, key=str),
        created_at=rollup.created_at,
    )


def _entity_to_out(entity: GroupEntity) -> GroupOut:
    if isinstance(entity, RollupGroup):
        return _rollup_to_out(entity)
    if isinstance(entity, SourceGroup):
        return SourceGroupOut.model_validate(entity)
    return LabelOut.model_validate(entity)


def _public_dashboard_holding(holding, allowed_group_names: set[str]) -> SharedDashboardHoldingOut:
    return SharedDashboardHoldingOut(
        ticker=holding.ticker,
        name=holding.name,
        market=holding.market,
        currency=holding.currency,
        quantity=holding.quantity,
        remaining_cost_basis=holding.remaining_cost_basis,
        current_price=holding.current_price,
        current_value=holding.current_value,
        current_value_change=holding.current_value_change,
        unrealized_profit_loss=holding.unrealized_profit_loss,
        groups=[
            SharedDashboardHoldingGroupBadgeOut(
                name=badge.name,
                color=badge.color,
                remaining_quantity=badge.remaining_quantity,
            )
            for badge in holding.groups
            if badge.name in allowed_group_names
        ],
    )


def _public_shared_dashboard(dashboard: DashboardResponse) -> SharedDashboardOut:
    group_keys = {
        (group.kind, group.id): f"group-{index}"
        for index, group in enumerate(dashboard.groups, start=1)
    }
    groups = [
        SharedDashboardGroupOut(
            key=group_keys[(group.kind, group.id)],
            kind="source",
            name=group.name,
            color=group.color,
            summary=group.summary,
            holdings=[
                _public_dashboard_holding(holding, {group.name})
                for holding in group.holdings
            ],
        )
        for group in dashboard.groups
        if group.kind == "source"
    ]
    history_rows = []
    for row in dashboard.history.rows:
        if row.group_kind == "total":
            group_key = "total"
        else:
            group_key = group_keys.get((row.group_kind, row.group_id))
            if group_key is None or row.group_kind != "source":
                continue
        history_rows.append(
            SharedDashboardHistoryRowOut(
                group_key=group_key,
                group_kind=row.group_kind,
                group_name=row.group_name,
                snapshot_date=row.snapshot_date,
                total_value=row.total_value,
                total_invested_principal=row.total_invested_principal,
                total_cost_basis=row.total_cost_basis,
                total_profit_loss=row.total_profit_loss,
            )
        )
    return SharedDashboardOut(
        display_currency=dashboard.display_currency,
        summary=dashboard.summary,
        groups=groups,
        history=SharedDashboardHistoryOut(rows=history_rows),
        holdings=[
            _public_dashboard_holding(
                holding,
                {group.name for group in dashboard.groups if group.kind == "source"},
            )
            for holding in dashboard.holdings
        ],
    )


async def _get_owned_entity(
    db: AsyncSession,
    kind: GroupKind,
    entity_id: uuid.UUID,
    user_id: uuid.UUID,
) -> GroupEntity:
    model = _GROUP_MODELS[kind]
    query = select(model).where(model.id == entity_id).where(model.user_id == user_id)
    if model is RollupGroup:
        query = query.options(selectinload(RollupGroup.members))
    result = await db.execute(query)
    entity = result.scalar_one_or_none()
    if entity is None:
        raise _not_found()
    return entity


async def _validate_source_group_ids(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_group_ids: list[uuid.UUID],
) -> None:
    if not source_group_ids:
        return
    result = await db.execute(
        select(SourceGroup.id)
        .where(SourceGroup.user_id == user_id)
        .where(SourceGroup.id.in_(source_group_ids))
    )
    if set(result.scalars().all()) != set(source_group_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source group not found")


async def _has_reference(db: AsyncSession, model, *conditions) -> bool:
    result = await db.execute(select(model).where(*conditions).limit(1))
    return result.scalar_one_or_none() is not None


async def _ensure_not_referenced(db: AsyncSession, kind: GroupKind, entity_id: uuid.UUID) -> None:
    if kind == "sources":
        checks = (
            (Transaction, Transaction.source_group_id == entity_id),
            (BuyLot, BuyLot.source_group_id == entity_id),
            (RollupGroupMember, RollupGroupMember.source_group_id == entity_id),
        )
    elif kind == "labels":
        checks = ((TransactionLabel, TransactionLabel.label_id == entity_id),)
    else:
        checks = ((RollupGroupMember, RollupGroupMember.rollup_group_id == entity_id),)

    for model, condition in checks:
        if await _has_reference(db, model, condition):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Referenced group cannot be deleted",
            )


@router.get("/sources", response_model=list[SourceGroupOut])
async def list_source_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SourceGroup)
        .where(SourceGroup.user_id == current_user.id)
        .order_by(SourceGroup.created_at, SourceGroup.id)
    )
    return result.scalars().all()


@router.post("/sources", response_model=SourceGroupOut, status_code=status.HTTP_201_CREATED)
async def create_source_group(
    body: SourceGroupCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source = SourceGroup(user_id=current_user.id, share_requires_auth=True, **body.model_dump())
    db.add(source)
    await db.flush()
    return source


@router.get("/sources/{source_group_id}", response_model=SourceGroupOut)
async def get_source_group(
    source_group_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owned_entity(db, "sources", source_group_id, current_user.id)


@router.put("/sources/{source_group_id}", response_model=SourceGroupOut)
async def update_source_group(
    source_group_id: uuid.UUID,
    body: SourceGroupUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source = await _get_owned_entity(db, "sources", source_group_id, current_user.id)
    _apply_metadata(source, body)
    return source


@router.get("/labels", response_model=list[LabelOut])
async def list_labels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Label).where(Label.user_id == current_user.id).order_by(Label.created_at, Label.id)
    )
    return result.scalars().all()


@router.post("/labels", response_model=LabelOut, status_code=status.HTTP_201_CREATED)
async def create_label(
    body: LabelCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    label = Label(user_id=current_user.id, share_requires_auth=True, **body.model_dump())
    db.add(label)
    await db.flush()
    return label


@router.get("/labels/{label_id}", response_model=LabelOut)
async def get_label(
    label_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owned_entity(db, "labels", label_id, current_user.id)


@router.put("/labels/{label_id}", response_model=LabelOut)
async def update_label(
    label_id: uuid.UUID,
    body: LabelUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    label = await _get_owned_entity(db, "labels", label_id, current_user.id)
    _apply_metadata(label, body)
    return label


@router.get("/rollups", response_model=list[RollupGroupOut])
async def list_rollup_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RollupGroup)
        .where(RollupGroup.user_id == current_user.id)
        .order_by(RollupGroup.created_at, RollupGroup.id)
        .options(selectinload(RollupGroup.members))
    )
    return [_rollup_to_out(rollup) for rollup in result.scalars().all()]


@router.post("/rollups", response_model=RollupGroupOut, status_code=status.HTTP_201_CREATED)
async def create_rollup_group(
    body: RollupGroupCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _validate_source_group_ids(db, current_user.id, body.source_group_ids)
    rollup = RollupGroup(
        user_id=current_user.id,
        name=body.name,
        color=body.color,
        description=body.description,
        share_description=body.share_description,
        share_requires_auth=True,
    )
    db.add(rollup)
    await db.flush()
    for source_group_id in body.source_group_ids:
        db.add(RollupGroupMember(rollup_group_id=rollup.id, source_group_id=source_group_id))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rollup group membership conflict",
        )
    return _rollup_to_out(rollup, body.source_group_ids)


@router.get("/rollups/{rollup_group_id}", response_model=RollupGroupOut)
async def get_rollup_group(
    rollup_group_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rollup = await _get_owned_entity(db, "rollups", rollup_group_id, current_user.id)
    return _rollup_to_out(rollup)


@router.put("/rollups/{rollup_group_id}", response_model=RollupGroupOut)
async def update_rollup_group(
    rollup_group_id: uuid.UUID,
    body: RollupGroupUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rollup = await _get_owned_entity(db, "rollups", rollup_group_id, current_user.id)
    _apply_metadata(rollup, body)
    if body.source_group_ids is not None:
        await _validate_source_group_ids(db, current_user.id, body.source_group_ids)
        existing_members = {member.source_group_id: member for member in rollup.members}
        requested_ids = set(body.source_group_ids)
        for source_group_id, member in existing_members.items():
            if source_group_id not in requested_ids:
                await db.delete(member)
        for source_group_id in requested_ids - existing_members.keys():
            db.add(RollupGroupMember(rollup_group_id=rollup.id, source_group_id=source_group_id))
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Rollup group membership conflict",
            )
        return _rollup_to_out(rollup, body.source_group_ids)
    return _rollup_to_out(rollup)


@router.delete("/{kind}/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    kind: GroupKind,
    entity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _get_owned_entity(db, kind, entity_id, current_user.id)
    await _ensure_not_referenced(db, kind, entity_id)
    await db.delete(entity)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Referenced group cannot be deleted",
        )


@router.post("/{kind}/{entity_id}/share", response_model=GroupOut)
async def enable_share(
    kind: GroupKind,
    entity_id: uuid.UUID,
    body: ShareUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _get_owned_entity(db, kind, entity_id, current_user.id)
    entity.share_token = str(uuid.uuid4())
    entity.share_requires_auth = body.requires_auth
    return _entity_to_out(entity)


@router.delete("/{kind}/{entity_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def disable_share(
    kind: GroupKind,
    entity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _get_owned_entity(db, kind, entity_id, current_user.id)
    entity.share_token = None


@router.get("/share/{token}", response_model=SharedGroupOut)
async def get_shared_group(
    token: uuid.UUID,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    entity = None
    public_kind = None
    for model, kind in ((SourceGroup, "source"), (RollupGroup, "rollup"), (Label, "label")):
        result = await db.execute(select(model).where(model.share_token == str(token)))
        entity = result.scalar_one_or_none()
        if entity is not None:
            public_kind = kind
            break
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    if entity.share_requires_auth and current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    scope = await resolve_portfolio_scope(db, entity.user_id, public_kind, entity.id)
    dashboard = await build_shared_portfolio_dashboard(db, entity.user_id, scope)
    return SharedGroupOut(
        kind=public_kind,
        name=entity.name,
        color=entity.color,
        description=entity.description,
        share_description=entity.share_description,
        dashboard=_public_shared_dashboard(dashboard),
    )
