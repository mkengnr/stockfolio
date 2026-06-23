"""Market session policy: when a provider price_date may be persisted as a
confirmed close. Pure functions; no DB, no network. zoneinfo only."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.holding import Market

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")

_MARKET_TZ: dict[Market, ZoneInfo] = {Market.KRX: KST, Market.US: ET}
# KRX 정규장 15:30 마감 + 데이터 정착 버퍼 → 15:45. US 16:00 ET.
_DEFAULT_CLOSE: dict[Market, time] = {Market.KRX: time(15, 45), Market.US: time(16, 0)}


def market_local_date(market: Market, now: datetime) -> date:
    """Return the calendar date currently in effect for a market."""
    return now.astimezone(_MARKET_TZ[market]).date()


def _close_time(market: Market, on: date, close_overrides: dict[date, time] | None) -> time:
    if market == Market.KRX and close_overrides and on in close_overrides:
        return close_overrides[on]
    return _DEFAULT_CLOSE[market]


def is_write_confirmed(
    market: Market,
    price_date: date,
    now: datetime,
    *,
    close_overrides: dict[date, time] | None = None,
) -> bool:
    """True if `price_date` is a completed session for `market` as of `now`."""
    local = now.astimezone(_MARKET_TZ[market])
    market_today = market_local_date(market, now)
    if price_date < market_today:
        return True
    if price_date == market_today:
        return local.time() >= _close_time(market, price_date, close_overrides)
    return False


def safe_query_end(
    market: Market,
    now: datetime,
    *,
    close_overrides: dict[date, time] | None = None,
) -> date:
    """Calendar upper bound for backfill: today only if its session is confirmed."""
    local = now.astimezone(_MARKET_TZ[market])
    market_today = market_local_date(market, now)
    if local.time() >= _close_time(market, market_today, close_overrides):
        return market_today
    return market_today - timedelta(days=1)
