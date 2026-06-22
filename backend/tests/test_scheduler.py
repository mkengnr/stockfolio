from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.holding import Market
from app.tasks import scheduler as sch


def test_start_scheduler_registers_split_jobs_with_hardening():
    fake = MagicMock()
    with patch.object(sch, "scheduler", fake):
        sch.start_scheduler()
    jobs = {c.kwargs.get("id"): c for c in fake.add_job.call_args_list}
    assert {"krx_snapshot", "us_snapshot", "snapshot_backfill"} <= set(jobs)
    for jid in ("krx_snapshot", "us_snapshot"):
        kw = jobs[jid].kwargs
        assert kw["coalesce"] is True
        assert kw["max_instances"] == 1
        assert kw["misfire_grace_time"] == sch.settings.snapshot_misfire_grace_seconds


@pytest.mark.asyncio
async def test_startup_catchup_rebuilds_recent_window_to_correct_stale_prices():
    holding = SimpleNamespace(
        id="holding-id",
        ticker="005930",
        market=Market.KRX,
        first_buy_date=date(2026, 1, 1),
        transactions=[],
    )
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [holding]
    db.execute.return_value = result

    class SessionContext:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with (
        patch.object(sch, "AsyncSessionLocal", return_value=SessionContext()),
        patch.object(sch, "safe_query_end", return_value=date(2026, 6, 22)),
        patch.object(sch, "backfill_holding_snapshots", new=AsyncMock(return_value=0)),
        patch.object(sch, "rebuild_holding_snapshots", new=AsyncMock(return_value=14)) as rebuild,
        patch.object(sch, "_finalize", new=AsyncMock()),
    ):
        await sch._startup_catchup()

    rebuild.assert_awaited_once_with(
        db,
        holding,
        start=date(2026, 6, 8),
        end=date(2026, 6, 22),
    )
