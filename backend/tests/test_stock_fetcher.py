"""
Unit tests for stock_fetcher.py.
Network calls are mocked — these tests run without KRX/yfinance connectivity.
"""
from datetime import date
from decimal import Decimal
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.models.holding import Currency, Market
from app.routers.deps import get_current_user
from app.routers.stocks import router as stocks_router
from app.services.stock_fetcher import (
    OHLCBar,
    PriceResult,
    StockSearchResult,
    detect_currency,
    detect_market,
    get_current_price,
    get_price_history,
    get_price_on_date,
    search_stocks,
)


# ---------------------------------------------------------------------------
# detect_market
# ---------------------------------------------------------------------------

class TestDetectMarket:
    def test_six_digit_numeric_is_krx(self):
        assert detect_market("005930") == Market.KRX

    def test_leading_zeros_still_krx(self):
        assert detect_market("000660") == Market.KRX

    def test_six_character_krx_code_with_letter_is_krx(self):
        assert detect_market("0195R0") == Market.KRX

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

    @patch("app.services.stock_fetcher.krx.get_etf_ticker_name", return_value="KODEX 200")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_name", return_value="")
    @patch("app.services.stock_fetcher.krx.get_market_ohlcv_by_date")
    def test_falls_back_to_etf_name_for_etf_ticker(self, mock_ohlcv, mock_market_name, mock_etf_name):
        mock_ohlcv.return_value = _make_krx_df(49_850)
        result = get_current_price("069500")
        assert result.name == "KODEX 200"

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
        mock_ticker.history.assert_called_once_with(period="5d", auto_adjust=False)

    @patch("app.services.stock_fetcher.yf.Ticker")
    def test_falls_back_to_short_name(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "", "shortName": "TSLA"}
        mock_ticker.history.return_value = _make_yf_history(250.0)
        mock_ticker_cls.return_value = mock_ticker

        result = get_current_price("TSLA")
        assert result.name == "TSLA"

    @patch("app.services.stock_fetcher.yf.Ticker")
    def test_uses_last_valid_close_when_latest_bar_is_nan(self, mock_ticker_cls):
        df = _make_yf_history(33.85)
        trailing_nan = pd.DataFrame(
            {"Open": [34.0], "High": [34.0], "Low": [34.0], "Close": [float("nan")], "Volume": [0]},
            index=pd.DatetimeIndex([pd.Timestamp("2024-01-16")]),
        )
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Dow Inc."}
        mock_ticker.history.return_value = pd.concat([df, trailing_nan])
        mock_ticker_cls.return_value = mock_ticker

        result = get_current_price("DOW")
        assert result.price == Decimal("33.85")
        assert result.price_date == date(2024, 1, 15)

    @patch("app.services.stock_fetcher.yf.Ticker")
    def test_all_nan_close_raises_like_empty_history(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Dow Inc."}
        mock_ticker.history.return_value = _make_yf_history(float("nan"))
        mock_ticker_cls.return_value = mock_ticker

        with pytest.raises(ValueError, match="No yfinance price data"):
            get_current_price("DOW")

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

    @patch("app.services.stock_fetcher.yf.Ticker")
    def test_us_history_uses_unadjusted_close(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_yf_history(185.5)
        mock_ticker_cls.return_value = mock_ticker

        bars = get_price_history("AAPL", date(2024, 1, 15), date(2024, 1, 15))

        assert bars[0].close == Decimal("185.5")
        mock_ticker.history.assert_called_once_with(
            start="2024-01-15",
            end="2024-01-16",
            auto_adjust=False,
        )


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


# ---------------------------------------------------------------------------
# search_stocks
# ---------------------------------------------------------------------------

class TestSearchStocks:
    @pytest.mark.parametrize(
        ("query", "code", "name"),
        [
            ("삼성전자", "005930", "삼성전자"),
            ("하이닉스", "000660", "SK하이닉스"),
        ],
    )
    @patch("app.services.stock_fetcher.yf.Search")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_list")
    @patch("app.services.stock_fetcher.urlopen")
    def test_korean_name_search_uses_naver_autocomplete(
        self,
        mock_urlopen,
        mock_ticker_list,
        mock_yf_search,
        query,
        code,
        name,
    ):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "query": query,
            "items": [
                {
                    "code": code,
                    "name": name,
                    "nationCode": "KOR",
                    "category": "stock",
                },
            ],
        }).encode()
        mock_urlopen.return_value = response

        results = search_stocks(query, limit=10)

        assert results == [
            StockSearchResult(
                ticker=code,
                name=name,
                market=Market.KRX,
                currency=Currency.KRW,
            ),
        ]
        mock_ticker_list.assert_not_called()
        mock_yf_search.assert_not_called()

    @patch("app.services.stock_fetcher.urlopen", side_effect=RuntimeError("network down"))
    @patch("app.services.stock_fetcher.yf.Search")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_name")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_list")
    def test_krx_search_matches_partial_code_and_name(
        self,
        mock_ticker_list,
        mock_ticker_name,
        mock_yf_search,
        mock_urlopen,
    ):
        mock_ticker_list.return_value = ["005930", "000660", "035720"]
        mock_ticker_name.side_effect = {
            "005930": "삼성전자",
            "000660": "SK하이닉스",
            "035720": "카카오",
        }.get
        mock_yf_search.return_value.quotes = []

        results = search_stocks("삼성", limit=10)

        assert results == [
            StockSearchResult(
                ticker="005930",
                name="삼성전자",
                market=Market.KRX,
                currency=Currency.KRW,
            ),
        ]

    @patch("app.services.stock_fetcher.yf.Search")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_name")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_list")
    def test_krx_search_honors_limit(
        self,
        mock_ticker_list,
        mock_ticker_name,
        mock_yf_search,
    ):
        mock_ticker_list.return_value = ["005930", "005935"]
        mock_ticker_name.side_effect = ["삼성전자", "삼성전자우"]

        results = search_stocks("0059", limit=1)

        assert [result.ticker for result in results] == ["005930"]
        mock_yf_search.assert_not_called()

    @patch("app.services.stock_fetcher.yf.Search")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_list", return_value=[])
    def test_us_search_normalizes_yfinance_quotes(self, mock_ticker_list, mock_yf_search):
        mock_yf_search.return_value.quotes = [
            None,
            {"symbol": "AAPL", "longname": "Apple Inc.", "quoteType": "EQUITY"},
            {"symbol": "AAPL240621C00100000", "shortname": "Apple Call", "quoteType": "OPTION"},
            {"symbol": "MSFT", "shortname": "Microsoft Corporation", "quoteType": "EQUITY"},
        ]

        results = search_stocks("apple", limit=2)

        assert results == [
            StockSearchResult(
                ticker="AAPL",
                name="Apple Inc.",
                market=Market.US,
                currency=Currency.USD,
            ),
            StockSearchResult(
                ticker="MSFT",
                name="Microsoft Corporation",
                market=Market.US,
                currency=Currency.USD,
            ),
        ]
        mock_yf_search.assert_called_once_with(
            "apple",
            max_results=2,
            news_count=0,
            lists_count=0,
            recommended=0,
            timeout=5,
            raise_errors=False,
        )

    @patch("app.services.stock_fetcher.urlopen", side_effect=RuntimeError("network down"))
    @patch("app.services.stock_fetcher.krx.get_market_ticker_name", return_value="SK하이닉스")
    @patch("app.services.stock_fetcher.yf.Search")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_list", return_value=[])
    def test_yfinance_korean_listing_falls_back_to_krx_result(
        self,
        mock_ticker_list,
        mock_yf_search,
        mock_ticker_name,
        mock_urlopen,
    ):
        mock_yf_search.return_value.quotes = [
            {"symbol": "000660.KS", "longname": "SK hynix Inc.", "quoteType": "EQUITY"},
        ]

        results = search_stocks("SK하이닉스", limit=10)

        assert results == [
            StockSearchResult(
                ticker="000660",
                name="SK하이닉스",
                market=Market.KRX,
                currency=Currency.KRW,
            ),
        ]

    @patch("app.services.stock_fetcher.yf.Search", side_effect=RuntimeError("network down"))
    @patch("app.services.stock_fetcher.krx.get_market_ticker_list", return_value=[])
    def test_us_search_returns_empty_list_on_external_failure(self, mock_ticker_list, mock_yf_search):
        assert search_stocks("AAPL", limit=10) == []

    @patch("app.services.stock_fetcher.yf.Search")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_list", side_effect=RuntimeError("network down"))
    def test_krx_search_returns_us_results_when_krx_lookup_fails(self, mock_ticker_list, mock_yf_search):
        mock_yf_search.return_value.quotes = [
            {"symbol": "TSLA", "shortname": "Tesla, Inc.", "quoteType": "EQUITY"},
        ]

        results = search_stocks("TSLA", limit=10)

        assert [result.ticker for result in results] == ["TSLA"]

    @patch("app.services.stock_fetcher.yf.Search")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_list", return_value=[])
    def test_caps_limit_for_direct_service_calls(self, mock_ticker_list, mock_yf_search):
        mock_yf_search.return_value.quotes = []

        search_stocks("AAPL", limit=100)

        assert mock_yf_search.call_args.kwargs["max_results"] == 20

    @patch("app.services.stock_fetcher.yf.Search")
    @patch("app.services.stock_fetcher.krx.get_market_ticker_list")
    def test_blank_query_skips_external_lookups(self, mock_ticker_list, mock_yf_search):
        assert search_stocks(" ") == []
        mock_ticker_list.assert_not_called()
        mock_yf_search.assert_not_called()


# ---------------------------------------------------------------------------
# GET /api/stocks/search
# ---------------------------------------------------------------------------

def _stocks_test_client(*, authenticated: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(stocks_router)

    if authenticated:
        async def _authenticated_user():
            return SimpleNamespace(id="user-id")

        app.dependency_overrides[get_current_user] = _authenticated_user
    else:
        async def _unauthenticated_user():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        app.dependency_overrides[get_current_user] = _unauthenticated_user

    return TestClient(app)


class TestSearchStocksRoute:
    @patch("app.routers.stocks.search_stocks")
    def test_returns_search_results_for_authenticated_user(self, mock_search_stocks):
        mock_search_stocks.return_value = [
            StockSearchResult("AAPL", "Apple Inc.", Market.US, Currency.USD),
        ]

        response = _stocks_test_client().get("/api/stocks/search", params={"q": "apple", "limit": 5})

        assert response.status_code == 200
        assert response.json() == [
            {"ticker": "AAPL", "name": "Apple Inc.", "market": "US", "currency": "USD"},
        ]
        mock_search_stocks.assert_called_once_with("apple", 5)

    def test_requires_authentication(self):
        response = _stocks_test_client(authenticated=False).get(
            "/api/stocks/search",
            params={"q": "apple"},
        )

        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("params", "expected_status"),
        [
            ({}, 422),
            ({"q": ""}, 422),
            ({"q": " "}, 422),
            ({"q": "apple", "limit": 0}, 422),
            ({"q": "apple", "limit": 21}, 422),
        ],
    )
    def test_validates_query_and_limit(self, params, expected_status):
        response = _stocks_test_client().get("/api/stocks/search", params=params)

        assert response.status_code == expected_status
