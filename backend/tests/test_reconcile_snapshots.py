"""Unit tests for classify_snapshot_rows — pure function only.
DB/network calls in main() are not tested here."""
from datetime import date

from scripts.reconcile_daily_snapshots import classify_snapshot_rows


def test_classify_detects_holiday_and_missing():
    existing = {date(2026, 6, 19), date(2026, 6, 22)}     # 6/19 US 휴장(잘못된 행)
    provider = {date(2026, 6, 18), date(2026, 6, 22)}     # 실제 거래일
    plan = classify_snapshot_rows(existing, provider)
    assert plan["delete"] == [date(2026, 6, 19)]          # 제공자에 없음 → 삭제
    assert plan["add"] == [date(2026, 6, 18)]             # 누락 → 추가
    assert plan["keep"] == [date(2026, 6, 22)]
