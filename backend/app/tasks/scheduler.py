"""
APScheduler tasks.
- Daily snapshot: runs at KST 15:35 (UTC 06:35) on weekdays.
"""
import asyncio
import logging
from datetime import date
from decimal import Decimal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.holding import Holding
from app.models.snapshot import DailySnapshot
from app.services.stock_fetcher import get_current_price
from app.services.snapshot_service import backfill_holding_snapshots

settings = get_settings()
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
logger = logging.getLogger(__name__)


async def _backfill_missing_snapshots() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Holding)
            .where(Holding.is_active == True)
            .options(selectinload(Holding.transactions))
        )
        for holding in result.scalars().all():
            try:
                added = await backfill_holding_snapshots(db, holding)
                if added:
                    logger.info("Backfilled %s snapshots for holding_id=%s", added, holding.id)
            except Exception:
                logger.exception("Failed to backfill snapshots for holding_id=%s", holding.id)
        await db.commit()


async def _save_daily_snapshots() -> None:
    today = date.today()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Holding).where(Holding.is_active == True)
        )
        holdings = result.scalars().all()
        for h in holdings:
            try:
                pr = await asyncio.to_thread(get_current_price, h.ticker)
                close_price = pr.price
            except Exception:
                continue

            # Upsert snapshot
            existing = await db.execute(
                select(DailySnapshot)
                .where(DailySnapshot.holding_id == h.id)
                .where(DailySnapshot.snapshot_date == today)
            )
            snap = existing.scalar_one_or_none()
            total_value = h.quantity * close_price
            if snap:
                snap.close_price = close_price
                snap.total_value = total_value
            else:
                db.add(DailySnapshot(
                    holding_id=h.id,
                    snapshot_date=today,
                    close_price=close_price,
                    total_value=total_value,
                ))
        await db.commit()


def start_scheduler() -> None:
    scheduler.add_job(
        _backfill_missing_snapshots,
        trigger="date",
        id="snapshot_backfill",
        replace_existing=True,
    )
    scheduler.add_job(
        _save_daily_snapshots,
        trigger=CronTrigger(
            hour=settings.snapshot_cron_hour,
            minute=settings.snapshot_cron_minute,
            day_of_week="mon-fri",
            timezone="Asia/Seoul",
        ),
        id="daily_snapshot",
        replace_existing=True,
    )
    scheduler.start()
