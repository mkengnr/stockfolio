from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


@dataclass(frozen=True)
class ExchangeRate:
    base: str
    quote: str
    rate: Decimal
    as_of: datetime


_CACHE_TTL = timedelta(minutes=30)
_usd_krw_rate_cache: tuple[ExchangeRate, datetime] | None = None


def clear_usd_krw_rate_cache() -> None:
    global _usd_krw_rate_cache
    _usd_krw_rate_cache = None


def convert_money(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    rate: ExchangeRate | None,
) -> Decimal:
    if from_currency == to_currency:
        return amount
    if rate is None:
        raise ValueError("Exchange rate is required for cross-currency conversion")
    if rate.base != "USD" or rate.quote != "KRW":
        raise ValueError("Unsupported exchange rate pair")

    if from_currency == "USD" and to_currency == "KRW":
        return amount * rate.rate
    if from_currency == "KRW" and to_currency == "USD":
        return amount / rate.rate
    raise ValueError(f"Unsupported currency conversion: {from_currency} -> {to_currency}")


def get_usd_krw_rate(
    *,
    ticker_factory: Callable[[str], object] | None = None,
    now_factory: Callable[[], datetime] | None = None,
    force_refresh: bool = False,
) -> ExchangeRate:
    global _usd_krw_rate_cache

    now = now_factory() if now_factory is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    use_cache = ticker_factory is None
    if (
        use_cache
        and not force_refresh
        and _usd_krw_rate_cache is not None
        and now - _usd_krw_rate_cache[1] < _CACHE_TTL
    ):
        return _usd_krw_rate_cache[0]

    if ticker_factory is None:
        import yfinance as yf

        ticker_factory = yf.Ticker

    ticker = ticker_factory("USDKRW=X")
    history = ticker.history(period="5d")
    if getattr(history, "empty", False):
        raise ValueError("USD/KRW exchange rate unavailable")

    try:
        latest = history.iloc[-1]
        close = latest["Close"]
        as_of = history.index[-1]
    except Exception as exc:
        raise ValueError("USD/KRW exchange rate unavailable") from exc

    if close is None:
        raise ValueError("USD/KRW exchange rate unavailable")

    if isinstance(as_of, datetime):
        as_of_datetime = as_of
    elif hasattr(as_of, "to_pydatetime"):
        as_of_datetime = as_of.to_pydatetime()
    else:
        as_of_datetime = datetime.combine(as_of, datetime.min.time())
    if as_of_datetime.tzinfo is None:
        as_of_datetime = as_of_datetime.replace(tzinfo=timezone.utc)

    rate = ExchangeRate(
        base="USD",
        quote="KRW",
        rate=Decimal(str(close)),
        as_of=as_of_datetime,
    )
    if use_cache:
        _usd_krw_rate_cache = (rate, now)
    return rate
