"""
Unit tests for stock_fetcher.py.
Network calls are mocked — these tests run without KRX/yfinance connectivity.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.models.holding import Currency, Market
from app.services.stock_fetcher import (
    OHLCBar,
    PriceResult,
    detect_currency,
    detect_market,
    get_current_price,
    get_price_history,
    get_price_on_date,
)


# ---------------------------------------------------------------------------
# detect_market
# ---------------------------------------------------------------------------

class TestDetectMarket:
    def test_six_digit_numeric_is_krx(self):
        assert detect_market("005930") == Market.KRX

    def test_leading_zeros_still_krx(self):
        assert detect_market("000660") == Market.KRX

    def test_alphabetic_ticker_is_us(self):
        assert detect_market("AAPL") == Market.US

    def test_mixed_alphanumeric_is_us(self):
        assert detect_market("BRK.B") == Market.US

    def test_five_digit_is_us(self):
        assert detect_market("12345") == Market.US

    def test_seven_digit_is_us(self):
        assert detect_market("0059300") == Market.US

    def test_tsla_is_us(self):
        assert detect_market("TSLA") == Market.US


# ---------------------------------------------------------------------------
# detect_currency
# ---------------------------------------------------------------------------

class TestDetectCurrency:
    def test_krx_gives_krw(self):
        assert detect_currency(Market.KRX) == Currency.KRW

    def test_us_gives_usd(self):
        assert detect_currency(Market.US) == Currency.USD


# ---------------------------------------------------------------------------
# get_current_price  — KRX path
# ---------------------------------------------------------------------------

def _make_krx_df(close: int) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp("2024-01-15")])
    return pd.DataFrame({"종가": [close], "거래량": [100_000]}, index=idx)


class TestGetCurrentPriceKRX:
    @patch("app.services.stock_fetcher.krx.get_market_ticker_name", return_value="삼성전자")
    @patch("app.services.stock_fetcher.krx.get_market_ohlcv_by_date")
    def test_returns_price_result(self, mock_ohlcv, mock_name):
        mock_ohlcv.return_value = _make_krx_df(75_000)
        result = get_current_price("005930")

        assert isinstance(result, PriceResult)
        assert result.ticker == "005930"
        assert result.market == Market.KRX
        assert result.name == "삼성전자"
        assert result.currency == Currency.KRW
        assert result.price == Decimal("75000")
        assert result.price_date == date(2024, 1, 15)

    @patch("app.services.stock_fetcher.krx.get_market_ticker_name", return_value="")
    @patch("app.services.stock_fetcher.krx.get_market_ohlcv_by_date")
    def test_falls_back_to_ticker_when_name_empty(self, mock_ohlcv, mock_name):
        mock_ohlcv.return_value = _make_krx_df(50_000)
        result = get_current_price("000660")
        assert result.name == "000660"

    @patch("app.services.stock_fetcher.krx.get_market_ticker_name", return_value="삼성전자")
    @patch("app.services.stock_fetcher.krx.get_market_ohlcv_by_date", return_value=pd.DataFrame())
    def test_raises_on_empty_df(self, mock_ohlcv, mock_name):
        with pytest.raises(ValueError, match="No KRX price data"):
            get_current_price("005930")


# ---------------------------------------------------------------------------
# get_current_price  — US path
# ---------------------------------------------------------------------------

def _make_yf_history(close: float) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp("2024-01-15")])
    return pd.DataFrame({
        "Open": [close - 1], "High": [close + 2], "Low": [close - 2],
        "Close": [close], "Volume": [50_000_000],
    }, index=idx)


class TestGetCurrentPriceUS:
    @patch("app.services.stock_fetcher.yf.Ticker")
    def test_returns_price_result(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Apple Inc.", "shortName": "Apple"}
        mock_ticker.history.return_value = _make_yf_history(185.5)
        mock_ticker_cls.return_value = mock_ticker

        result = get_current_price("AAPL")
        assert result.market == Market.US
        assert result.name == "Apple Inc."
        assert result.currency == Currency.USD
        assert result.price == Decimal("185.5")

    @patch("app.services.stock_fetcher.yf.Ticker")
    def test_falls_back_to_short_name(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "", "shortName": "TSLA"}
        mock_ticker.history.return_value = _make_yf_history(250.0)
        mock_ticker_cls.return_value = mock_ticker

        result = get_current_price("TSLA")
        assert result.name == "TSLA"

    @patch("app.services.stock_fetcher.yf.Ticker")
    def test_raises_on_empty_history(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Unknown"}
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        with pytest.raises(ValueError, match="No yfinance price data"):
            get_current_price("FAKE")


# ---------------------------------------------------------------------------
# get_price_history
# ---------------------------------------------------------------------------

def _make_krx_history_df() -> pd.DataFrame:
    dates = pd.DatetimeIndex([pd.Timestamp("2024-01-10"), pd.Timestamp("2024-01-11")])
    return pd.DataFrame({
        "시가": [74_000, 75_000],
        "고가": [76_000, 76_500],
        "저가": [73_500, 74_800],
        "종가": [75_000, 76_000],
        "거래량": [1_000_000, 900_000],
    }, index=dates)


class TestGetPriceHistory:
    @patch("app.services.stock_fetcher.krx.get_market_ohlcv_by_date")
    def test_krx_history_returns_bars(self, mock_ohlcv):
        mock_ohlcv.return_value = _make_krx_history_df()
        bars = get_price_history("005930", date(2024, 1, 10), date(2024, 1, 11))

        assert len(bars) == 2
        assert all(isinstance(b, OHLCBar) for b in bars)
        assert bars[0].close == Decimal("75000")
        assert bars[1].close == Decimal("76000")

    @patch("app.services.stock_fetcher.krx.get_market_ohlcv_by_date", return_value=pd.DataFrame())
    def test_empty_df_returns_empty_list(self, mock_ohlcv):
        bars = get_price_history("005930", date(2024, 1, 10), date(2024, 1, 11))
        assert bars == []


# ---------------------------------------------------------------------------
# get_price_on_date
# ---------------------------------------------------------------------------

class TestGetPriceOnDate:
    @patch("app.services.stock_fetcher.krx.get_market_ohlcv_by_date")
    def test_returns_last_close(self, mock_ohlcv):
        mock_ohlcv.return_value = _make_krx_history_df()
        price = get_price_on_date("005930", date(2024, 1, 11))
        assert price == Decimal("76000")

    @patch("app.services.stock_fetcher.krx.get_market_ohlcv_by_date", return_value=pd.DataFrame())
    def test_returns_none_when_no_data(self, mock_ohlcv):
        price = get_price_on_date("005930", date(2024, 1, 11))
        assert price is None
