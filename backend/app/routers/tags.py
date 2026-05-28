import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.holding import Holding
from app.models.tag import HoldingTag, Tag
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.tag import (
    TagCreateIn, TagDetailOut, TagOut, TagShareUpdateIn, TagSummary, TagUpdateIn,
)
from app.services.price_cache import get_price

router = APIRouter(prefix="/api/tags", tags=["tags"])


async def _compute_summary(holdings: list[Holding]) -> TagSummary:
    total_cost = Decimal(0)
    total_current = Decimal(0)
    has_prices = True
    for h in holdings:
        if not h.is_active:
            continue
        cost = h.quantity * h.avg_price
        total_cost += cost
        try:
            pr = await get_price(h.ticker)
            total_current += h.quantity * pr.price
        except Exception:
            has_prices = False

    pl = (total_current - total_cost) if has_prices else None
    pl_pct = (pl / total_cost * 100) if (pl is not None and total_cost > 0) else None
    return TagSummary(
        total_cost_basis=total_cost,
        total_current_value=total_current if has_prices else None,
        total_profit_loss=pl,
        total_profit_loss_pct=pl_pct,
        holding_count=sum(1 for h in holdings if h.is_active),
    )


def _tag_to_out(tag: Tag) -> TagOut:
    return TagOut(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        description=tag.description,
        share_token=tag.share_token,
        share_requires_auth=tag.share_requires_auth,
        holding_ids=[ht.holding_id for ht in tag.holding_tags],
        created_at=tag.created_at,
    )


@router.get("", response_model=list[TagOut])
async def list_tags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Tag)
        .where(Tag.user_id == current_user.id)
        .options(selectinload(Tag.holding_tags))
    )
    return [_tag_to_out(t) for t in result.scalars().all()]


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tag = Tag(user_id=current_user.id, name=body.name, color=body.color, description=body.description)
    db.add(tag)
    await db.flush()
    await db.refresh(tag, ["holding_tags"])
    return _tag_to_out(tag)


@router.get("/{tag_id}", response_model=TagDetailOut)
async def get_tag(
    tag_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Tag)
        .where(Tag.id == tag_id)
        .where(Tag.user_id == current_user.id)
        .options(selectinload(Tag.holding_tags).selectinload(HoldingTag.holding).selectinload(Holding.transactions))
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    holdings = [ht.holding for ht in tag.holding_tags]
    summary = await _compute_summary(holdings)
    out = TagDetailOut(**_tag_to_out(tag).model_dump(), summary=summary)
    return out


@router.put("/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: uuid.UUID,
    body: TagUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Tag)
        .where(Tag.id == tag_id)
        .where(Tag.user_id == current_user.id)
        .options(selectinload(Tag.holding_tags))
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    if body.name is not None:
        tag.name = body.name
    if body.color is not None:
        tag.color = body.color
    if body.description is not None:
        tag.description = body.description
    return _tag_to_out(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Tag).where(Tag.id == tag_id).where(Tag.user_id == current_user.id)
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    await db.delete(tag)


@router.post("/{tag_id}/holdings/{holding_id}", status_code=status.HTTP_201_CREATED)
async def add_holding_to_tag(
    tag_id: uuid.UUID,
    holding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tag_r = await db.execute(select(Tag).where(Tag.id == tag_id).where(Tag.user_id == current_user.id))
    tag = tag_r.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    holding_r = await db.execute(
        select(Holding).where(Holding.id == holding_id).where(Holding.user_id == current_user.id)
    )
    holding = holding_r.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")

    existing = await db.execute(
        select(HoldingTag).where(HoldingTag.holding_id == holding_id).where(HoldingTag.tag_id == tag_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Holding already in tag")

    db.add(HoldingTag(holding_id=holding_id, tag_id=tag_id))
    return {"status": "added"}


@router.delete("/{tag_id}/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_holding_from_tag(
    tag_id: uuid.UUID,
    holding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(HoldingTag).where(HoldingTag.holding_id == holding_id).where(HoldingTag.tag_id == tag_id)
    )
    ht = result.scalar_one_or_none()
    if ht is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Association not found")
    await db.delete(ht)


@router.post("/{tag_id}/share", response_model=TagOut)
async def enable_share(
    tag_id: uuid.UUID,
    body: TagShareUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Tag)
        .where(Tag.id == tag_id)
        .where(Tag.user_id == current_user.id)
        .options(selectinload(Tag.holding_tags))
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    tag.share_token = str(uuid.uuid4())
    tag.share_requires_auth = body.requires_auth
    return _tag_to_out(tag)


@router.delete("/{tag_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def disable_share(
    tag_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Tag).where(Tag.id == tag_id).where(Tag.user_id == current_user.id)
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    tag.share_token = None


# ---------------------------------------------------------------------------
# Public share endpoint
# ---------------------------------------------------------------------------

share_router = APIRouter(prefix="/api/share", tags=["share"])


@share_router.get("/{token}", response_model=TagDetailOut)
async def get_shared_tag(
    token: str,
    current_user: User | None = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Tag)
        .where(Tag.share_token == token)
        .options(selectinload(Tag.holding_tags).selectinload(HoldingTag.holding).selectinload(Holding.transactions))
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    if tag.share_requires_auth and current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    holdings = [ht.holding for ht in tag.holding_tags]
    summary = await _compute_summary(holdings)
    return TagDetailOut(**_tag_to_out(tag).model_dump(), summary=summary)
