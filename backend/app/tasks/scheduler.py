"""APScheduler tasks (in-process). KRX finalize at KST 15:45 (mon-fri),
US finalize at KST 06:30 (tue-sat). Startup catch-up backfills past sessions
and finalizes any already-closed market."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings, parse_market_close_overrides
from app.database import AsyncSessionLocal
from app.models.holding import Holding, Market
from app.services.market_session import safe_query_end
from app.services.price_cache import set_price
from app.services.snapshot_service import (
    backfill_holding_snapshots,
    finalize_market_snapshots,
    rebuild_holding_snapshots,
)

settings = get_settings()
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
logger = logging.getLogger(__name__)


def _close_overrides():
    return parse_market_close_overrides(settings.market_close_overrides_raw)


async def _active_holdings(db, market: Market):
    result = await db.execute(
        select(Holding).where(Holding.is_active == True)
        .options(selectinload(Holding.transactions))
    )
    return [h for h in result.scalars().all() if h.market == market]


async def _finalize(market: Market) -> None:
    now = datetime.now(tz=timezone.utc)
    overrides = _close_overrides()
    async with AsyncSessionLocal() as db:
        holdings = await _active_holdings(db, market)
        results = await finalize_market_snapshots(db, holdings, now, close_overrides=overrides)
        await db.commit()
        for holding, pr in results["confirmed"]:
            try:
                await set_price(holding.ticker, pr)
            except Exception:
                logger.warning("finalize redis set failed ticker=%s", holding.ticker, exc_info=True)
    if results["failed"]:
        logger.warning("%s finalize failed tickers=%s", market.value, results["failed"])


async def finalize_krx() -> None:
    await _finalize(Market.KRX)


async def finalize_us() -> None:
    await _finalize(Market.US)


async def _startup_catchup() -> None:
    now = datetime.now(tz=timezone.utc)
    overrides = _close_overrides()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Holding).where(Holding.is_active == True)
            .options(selectinload(Holding.transactions))
        )
        holdings = list(result.scalars().all())
        for holding in holdings:
            try:
                end = safe_query_end(holding.market, now, close_overrides=overrides)
                added = await backfill_holding_snapshots(db, holding, end=end)
                if added:
                    logger.info("Backfilled %s snapshots for holding_id=%s", added, holding.id)
                reconcile_start = max(
                    holding.first_buy_date,
                    end - timedelta(days=settings.snapshot_reconcile_days),
                )
                rebuilt = await rebuild_holding_snapshots(
                    db,
                    holding,
                    start=reconcile_start,
                    end=end,
                )
                if rebuilt:
                    logger.info(
                        "Reconciled %s recent snapshots for holding_id=%s",
                        rebuilt,
                        holding.id,
                    )
            except Exception:
                logger.exception("Failed to backfill snapshots for holding_id=%s", holding.id)
        await db.commit()
    for market in (Market.KRX, Market.US):
        await _finalize(market)


def start_scheduler() -> None:
    scheduler.add_job(_startup_catchup, trigger="date", id="snapshot_backfill", replace_existing=True)
    scheduler.add_job(
        finalize_krx,
        trigger=CronTrigger(
            hour=settings.krx_snapshot_hour,
            minute=settings.krx_snapshot_minute,
            day_of_week="mon-fri",
            timezone="Asia/Seoul",
        ),
        id="krx_snapshot",
        replace_existing=True,
        misfire_grace_time=settings.snapshot_misfire_grace_seconds,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        finalize_us,
        trigger=CronTrigger(
            hour=settings.us_snapshot_hour,
            minute=settings.us_snapshot_minute,
            day_of_week="tue-sat",
            timezone="Asia/Seoul",
        ),
        id="us_snapshot",
        replace_existing=True,
        misfire_grace_time=settings.snapshot_misfire_grace_seconds,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
