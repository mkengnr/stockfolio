"""Unit tests for classify_snapshot_rows — pure function only.
DB/network calls in main() are not tested here."""
from datetime import date

from decimal import Decimal
from pathlib import Path
import sys

from scripts import reconcile_daily_snapshots
from scripts.reconcile_daily_snapshots import classify_snapshot_rows


def test_cli_adds_backend_directory_to_import_path():
    assert reconcile_daily_snapshots.BACKEND_DIR == Path(__file__).resolve().parents[1]
    assert str(reconcile_daily_snapshots.BACKEND_DIR) in sys.path


def test_classify_detects_holiday_and_missing():
    existing = {
        date(2026, 6, 19): (Decimal("100"), Decimal("1000")),
        date(2026, 6, 22): (Decimal("110"), Decimal("1100")),
    }
    provider = {
        date(2026, 6, 18): (Decimal("100"), Decimal("1000")),
        date(2026, 6, 22): (Decimal("110"), Decimal("1100")),
    }
    plan = classify_snapshot_rows(existing, provider)
    assert plan["delete"] == [date(2026, 6, 19)]          # 제공자에 없음 → 삭제
    assert plan["add"] == [date(2026, 6, 18)]             # 누락 → 추가
    assert plan["keep"] == [date(2026, 6, 22)]


def test_classify_detects_wrong_price_and_total_value_on_existing_date():
    existing = {
        date(2026, 6, 22): (Decimal("360500"), Decimal("20188000")),
    }
    provider = {
        date(2026, 6, 22): (Decimal("353500"), Decimal("19796000")),
    }

    plan = classify_snapshot_rows(existing, provider)

    assert plan["update"] == [date(2026, 6, 22)]
    assert plan["keep"] == []


def test_classify_ignores_values_equal_after_database_scale_rounding():
    existing = {
        date(2025, 10, 16): (Decimal("603.770081"), Decimal("332.073545")),
    }
    provider = {
        date(2025, 10, 16): (
            Decimal("603.770081"),
            Decimal("332.07354455"),
        ),
    }

    plan = classify_snapshot_rows(existing, provider)

    assert plan["update"] == []
    assert plan["keep"] == [date(2025, 10, 16)]
