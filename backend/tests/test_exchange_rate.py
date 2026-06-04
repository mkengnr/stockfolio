import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.exchange_rate import (
    ExchangeRate,
    clear_usd_krw_rate_cache,
    convert_money,
    get_usd_krw_rate,
)


def test_convert_money_returns_same_currency_amount_without_rate():
    assert convert_money(Decimal("12.34"), "USD", "USD", None) == Decimal("12.34")


def test_convert_money_converts_usd_to_krw_with_rate():
    rate = ExchangeRate(
        base="USD",
        quote="KRW",
        rate=Decimal("1350.50"),
        as_of=datetime(2026, 6, 4, tzinfo=timezone.utc),
    )

    assert convert_money(Decimal("10"), "USD", "KRW", rate) == Decimal("13505.00")


def test_convert_money_converts_krw_to_usd_with_rate():
    rate = ExchangeRate(
        base="USD",
        quote="KRW",
        rate=Decimal("1350"),
        as_of=datetime(2026, 6, 4, tzinfo=timezone.utc),
    )

    assert convert_money(Decimal("2700"), "KRW", "USD", rate) == Decimal("2")


def test_convert_money_rejects_missing_rate_for_cross_currency_conversion():
    with pytest.raises(ValueError, match="Exchange rate is required"):
        convert_money(Decimal("1"), "USD", "KRW", None)


def test_convert_money_rejects_unsupported_conversion():
    rate = ExchangeRate(
        base="USD",
        quote="KRW",
        rate=Decimal("1350"),
        as_of=datetime(2026, 6, 4, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="Unsupported currency conversion"):
        convert_money(Decimal("1"), "EUR", "KRW", rate)


def test_get_usd_krw_rate_uses_injected_ticker_provider():
    as_of = datetime(2026, 6, 4, 12, tzinfo=timezone.utc)

    class _Ticker:
        def history(self, period):
            assert period == "5d"
            return SimpleNamespace(
                empty=False,
                index=[as_of],
                iloc=[{"Close": 1361.25}],
            )

    rate = get_usd_krw_rate(ticker_factory=lambda ticker: _Ticker())

    assert rate == ExchangeRate(
        base="USD",
        quote="KRW",
        rate=Decimal("1361.25"),
        as_of=as_of,
    )


def test_get_usd_krw_rate_caches_default_provider(monkeypatch):
    clear_usd_krw_rate_cache()
    calls = []
    as_of = datetime(2026, 6, 4, 12, tzinfo=timezone.utc)
    now = datetime(2026, 6, 4, 13, tzinfo=timezone.utc)

    class _Ticker:
        def history(self, period):
            return SimpleNamespace(
                empty=False,
                index=[as_of],
                iloc=[{"Close": 1361.25}],
            )

    def _ticker_factory(ticker):
        calls.append(ticker)
        return _Ticker()

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=_ticker_factory))

    first = get_usd_krw_rate(now_factory=lambda: now)
    second = get_usd_krw_rate(now_factory=lambda: now + timedelta(minutes=10))

    assert first == second
    assert calls == ["USDKRW=X"]
    clear_usd_krw_rate_cache()


def test_get_usd_krw_rate_rejects_empty_history():
    class _Ticker:
        def history(self, period):
            return SimpleNamespace(empty=True)

    with pytest.raises(ValueError, match="USD/KRW exchange rate unavailable"):
        get_usd_krw_rate(ticker_factory=lambda ticker: _Ticker())
