from unittest.mock import MagicMock, patch
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
