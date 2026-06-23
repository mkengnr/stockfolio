from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.models.holding import Market
from app.services.market_session import is_write_confirmed, market_local_date, safe_query_end

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


def _kst(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=KST)


def test_market_local_date_depends_on_market_timezone():
    now = datetime(2026, 6, 22, 23, 0, tzinfo=timezone.utc)

    assert market_local_date(Market.KRX, now) == date(2026, 6, 23)
    assert market_local_date(Market.US, now) == date(2026, 6, 22)


def test_krx_intraday_before_1545_not_confirmed():
    now = _kst(2026, 6, 22, 10, 8)
    assert is_write_confirmed(Market.KRX, date(2026, 6, 22), now) is False


def test_krx_confirmed_after_1545():
    now = _kst(2026, 6, 22, 15, 45)
    assert is_write_confirmed(Market.KRX, date(2026, 6, 22), now) is True


def test_past_session_always_confirmed():
    now = _kst(2026, 6, 22, 10, 0)
    assert is_write_confirmed(Market.KRX, date(2026, 6, 19), now) is True


def test_us_prior_session_confirmed_at_kst_morning():
    # KST 화 06:30 → US 월요일 세션은 마감(ET 16:00 월 = KST 05~06 화)
    now = _kst(2026, 6, 23, 6, 30)
    # provider price_date(미 직전 거래일)는 US 타임존 오늘보다 과거 → 확정
    assert is_write_confirmed(Market.US, date(2026, 6, 22), now) is True


def test_krx_override_blocks_until_1630():
    overrides = {date(2026, 11, 12): time(16, 30)}
    early = _kst(2026, 11, 12, 16, 29)
    late = _kst(2026, 11, 12, 16, 30)
    assert is_write_confirmed(Market.KRX, date(2026, 11, 12), early, close_overrides=overrides) is False
    assert is_write_confirmed(Market.KRX, date(2026, 11, 12), late, close_overrides=overrides) is True


def test_safe_query_end_excludes_today_before_close():
    now = _kst(2026, 6, 22, 10, 8)
    assert safe_query_end(Market.KRX, now) == date(2026, 6, 21)


def test_safe_query_end_includes_today_after_close():
    now = _kst(2026, 6, 22, 15, 45)
    assert safe_query_end(Market.KRX, now) == date(2026, 6, 22)
