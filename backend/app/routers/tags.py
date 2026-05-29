import asyncio
import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.holding import Holding
from app.models.tag import HoldingTag, Tag
from app.models.user import User
from app.routers.deps import get_current_user, get_current_user_optional
from app.schemas.tag import (
    SharedTagOut, TagCreateIn, TagDetailOut, TagOut, TagShareUpdateIn, TagSummary, TagUpdateIn,
)
from app.services.price_cache import get_price

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tags", tags=["tags"])


async def _compute_summary(holdings: list[Holding]) -> TagSummary:
    """Compute portfolio summary across the given holdings.

    Performance:
      - Deduplicates tickers before fetching prices.
      - Issues all price lookups in parallel via asyncio.gather.

    Failure mode:
      - If any individual price lookup fails, current-value-derived
        fields collapse to None and the failing ticker is logged.
        The summary's total_cost_basis and holding_count stay accurate.
    """
    active = [h for h in holdings if h.is_active]

    total_cost = sum((h.quantity * h.avg_price for h in active), Decimal(0))

    tickers = {h.ticker for h in active}
    if tickers:
        results = await asyncio.gather(
            *(get_price(t) for t in tickers),
            return_exceptions=True,
        )
        prices: dict[str, Decimal | None] = {}
        for ticker, res in zip(tickers, results):
            if isinstance(res, BaseException):
                logger.warning("price lookup failed for ticker=%s: %r", ticker, res)
                prices[ticker] = None
            else:
                prices[ticker] = res.price
    else:
        prices = {}

    has_prices = bool(prices) and all(p is not None for p in prices.values())
    total_current = Decimal(0)
    if has_prices:
        for h in active:
            total_current += h.quantity * prices[h.ticker]

    pl = (total_current - total_cost) if has_prices else None
    pl_pct = (pl / total_cost * 100) if (pl is not None and total_cost > 0) else None
    return TagSummary(
        total_cost_basis=total_cost,
        total_current_value=total_current if has_prices else None,
        total_profit_loss=pl,
        total_profit_loss_pct=pl_pct,
        holding_count=len(active),
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
        .options(selectinload(Tag.holding_tags).selectinload(HoldingTag.holding))
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
    try:
        await db.flush()
    except IntegrityError:
        # Two concurrent requests racing past the existence check — convert
        # the unique-constraint violation into a 409 instead of a 500.
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Holding already in tag")
    return {"status": "added"}


@router.delete("/{tag_id}/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_holding_from_tag(
    tag_id: uuid.UUID,
    holding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Ownership check via join — prevents deletion of associations belonging to other users
    result = await db.execute(
        select(HoldingTag)
        .join(Tag, HoldingTag.tag_id == Tag.id)
        .join(Holding, HoldingTag.holding_id == Holding.id)
        .where(HoldingTag.tag_id == tag_id)
        .where(HoldingTag.holding_id == holding_id)
        .where(Tag.user_id == current_user.id)
        .where(Holding.user_id == current_user.id)
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


@share_router.get("/{token}", response_model=SharedTagOut)
async def get_shared_tag(
    token: uuid.UUID,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Public-facing share endpoint.

    Returns SharedTagOut (no internal IDs / share token / holding IDs) so
    that share consumers cannot enumerate underlying resources. Token is
    typed as UUID to reject malformed input before any DB lookup.
    """
    result = await db.execute(
        select(Tag)
        .where(Tag.share_token == str(token))
        .options(selectinload(Tag.holding_tags).selectinload(HoldingTag.holding))
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    if tag.share_requires_auth and current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    holdings = [ht.holding for ht in tag.holding_tags]
    summary = await _compute_summary(holdings)
    return SharedTagOut(
        name=tag.name,
        color=tag.color,
        description=tag.description,
        summary=summary,
        holding_count=summary.holding_count,
    )
