"""
Stock data fetcher wrapping pykrx (KRX) and yfinance (US).

Market detection:
  - 6-digit numeric string  →  KRX
  - anything else            →  US (yfinance)
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yfinance as yf
from pykrx import stock as krx

from app.models.holding import Currency, Market

logger = logging.getLogger(__name__)

MAX_SEARCH_RESULTS = 20
YFINANCE_SEARCH_TIMEOUT_SECONDS = 5
NAVER_SEARCH_TIMEOUT_SECONDS = 3
NAVER_STOCK_AUTOCOMPLETE_URL = "https://ac.stock.naver.com/ac"
KOREAN_YFINANCE_SYMBOL = re.compile(r"^(?P<ticker>\d{6})\.(?:KS|KQ)$", re.IGNORECASE)


def detect_market(ticker: str) -> Market:
    """Return KRX for 6-digit numeric tickers, US otherwise."""
    return Market.KRX if re.fullmatch(r"\d{6}", ticker) else Market.US


def detect_currency(market: Market) -> Currency:
    return Currency.KRW if market == Market.KRX else Currency.USD


@dataclass
class PriceResult:
    ticker: str
    market: Market
    name: str
    currency: Currency
    price: Decimal
    price_date: date


@dataclass
class OHLCBar:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class StockSearchResult:
    ticker: str
    name: str
    market: Market
    currency: Currency


# ---------------------------------------------------------------------------
# KRX helpers
# ---------------------------------------------------------------------------

def _should_search_naver_krx(query: str) -> bool:
    return bool(re.search(r"[가-힣]", query)) or query.isdigit()


def _search_naver_krx(query: str, limit: int) -> list[StockSearchResult]:
    url = f"{NAVER_STOCK_AUTOCOMPLETE_URL}?{urlencode({'q': query, 'target': 'stock'})}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=NAVER_SEARCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
    except Exception:
        logger.warning("Naver KRX ticker search failed for query=%s", query, exc_info=True)
        return []

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []

    results = []
    seen_tickers = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        ticker = item.get("code")
        name = item.get("name")
        if (
            not isinstance(ticker, str)
            or not re.fullmatch(r"\d{6}", ticker)
            or not isinstance(name, str)
            or item.get("category") != "stock"
            or item.get("nationCode") != "KOR"
            or ticker in seen_tickers
        ):
            continue
        seen_tickers.add(ticker)
        results.append(
            StockSearchResult(
                ticker=ticker,
                name=name,
                market=Market.KRX,
                currency=Currency.KRW,
            )
        )
        if len(results) == limit:
            break
    return results


def _krx_name(ticker: str) -> str:
    try:
        return krx.get_market_ticker_name(ticker) or ticker
    except Exception:
        return ticker


def _krx_latest_price(ticker: str) -> tuple[Decimal, date]:
    today = date.today()
    # pykrx 날짜 형식: YYYYMMDD
    start = (today - timedelta(days=7)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    df = krx.get_market_ohlcv_by_date(start, end, ticker)
    if df is None or df.empty:
        raise ValueError(f"No KRX price data for {ticker}")
    last_row = df.iloc[-1]
    last_date = df.index[-1].date()
    return Decimal(str(last_row["종가"])), last_date


def _krx_history(ticker: str, start: date, end: date) -> list[OHLCBar]:
    df = krx.get_market_ohlcv_by_date(
        start.strftime("%Y%m%d"),
        end.strftime("%Y%m%d"),
        ticker,
    )
    if df is None or df.empty:
        return []
    bars = []
    for idx, row in df.iterrows():
        bars.append(OHLCBar(
            date=idx.date(),
            open=Decimal(str(row["시가"])),
            high=Decimal(str(row["고가"])),
            low=Decimal(str(row["저가"])),
            close=Decimal(str(row["종가"])),
            volume=int(row["거래량"]),
        ))
    return bars


def _search_krx(query: str, limit: int) -> list[StockSearchResult]:
    try:
        tickers = krx.get_market_ticker_list(market="ALL")
    except Exception:
        logger.warning("KRX ticker search failed", exc_info=True)
        return []

    normalized_query = query.casefold()
    results = []
    for ticker in tickers:
        name = _krx_name(ticker)
        if normalized_query not in ticker.casefold() and normalized_query not in name.casefold():
            continue
        results.append(
            StockSearchResult(
                ticker=ticker,
                name=name,
                market=Market.KRX,
                currency=Currency.KRW,
            )
        )
        if len(results) == limit:
            break
    return results


# ---------------------------------------------------------------------------
# US (yfinance) helpers
# ---------------------------------------------------------------------------

def _yf_info(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    return t.info


def _yf_latest_price(ticker: str) -> tuple[Decimal, date]:
    t = yf.Ticker(ticker)
    hist = t.history(period="5d")
    if hist.empty:
        raise ValueError(f"No yfinance price data for {ticker}")
    last_close = hist["Close"].iloc[-1]
    last_date = hist.index[-1].date()
    return Decimal(str(round(last_close, 6))), last_date


def _yf_history(ticker: str, start: date, end: date) -> list[OHLCBar]:
    t = yf.Ticker(ticker)
    df = t.history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat())
    if df.empty:
        return []
    bars = []
    for idx, row in df.iterrows():
        bars.append(OHLCBar(
            date=idx.date(),
            open=Decimal(str(round(row["Open"], 6))),
            high=Decimal(str(round(row["High"], 6))),
            low=Decimal(str(round(row["Low"], 6))),
            close=Decimal(str(round(row["Close"], 6))),
            volume=int(row["Volume"]),
        ))
    return bars


def _search_us(query: str, limit: int) -> list[StockSearchResult]:
    try:
        quotes = yf.Search(
            query,
            max_results=limit,
            news_count=0,
            lists_count=0,
            recommended=0,
            timeout=YFINANCE_SEARCH_TIMEOUT_SECONDS,
            raise_errors=False,
        ).quotes or []
    except Exception:
        logger.warning("yfinance ticker search failed for query=%s", query, exc_info=True)
        return []

    results = []
    seen_tickers = set()
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        ticker = quote.get("symbol")
        if not isinstance(ticker, str) or quote.get("quoteType") != "EQUITY":
            continue
        ticker = ticker.upper()
        korean_listing = KOREAN_YFINANCE_SYMBOL.fullmatch(ticker)
        normalized_ticker = korean_listing.group("ticker") if korean_listing else ticker
        if normalized_ticker in seen_tickers:
            continue
        seen_tickers.add(normalized_ticker)
        name = quote.get("longname") or quote.get("shortname")
        if not isinstance(name, str):
            name = normalized_ticker
        if korean_listing:
            krx_name = _krx_name(normalized_ticker)
            if krx_name != normalized_ticker:
                name = krx_name
        results.append(
            StockSearchResult(
                ticker=normalized_ticker,
                name=name,
                market=Market.KRX if korean_listing else Market.US,
                currency=Currency.KRW if korean_listing else Currency.USD,
            )
        )
        if len(results) == limit:
            break
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_current_price(ticker: str) -> PriceResult:
    """Fetch the most recent closing price for a ticker."""
    market = detect_market(ticker)
    currency = detect_currency(market)

    if market == Market.KRX:
        name = _krx_name(ticker)
        price, price_date = _krx_latest_price(ticker)
    else:
        info = _yf_info(ticker)
        name = info.get("longName") or info.get("shortName") or ticker
        price, price_date = _yf_latest_price(ticker)

    return PriceResult(
        ticker=ticker,
        market=market,
        name=name,
        currency=currency,
        price=price,
        price_date=price_date,
    )


def get_price_history(ticker: str, start: date, end: date) -> list[OHLCBar]:
    """Fetch OHLCV history for a date range (inclusive)."""
    market = detect_market(ticker)
    if market == Market.KRX:
        return _krx_history(ticker, start, end)
    return _yf_history(ticker, start, end)


def get_price_on_date(ticker: str, target_date: date) -> Decimal | None:
    """Return the closing price on or before target_date (looks back up to 7 days)."""
    start = target_date - timedelta(days=7)
    bars = get_price_history(ticker, start, target_date)
    if not bars:
        return None
    return bars[-1].close


def search_stocks(query: str, limit: int = 10) -> list[StockSearchResult]:
    """Search KRX and US equities for an autocomplete query."""
    query = query.strip()
    if not query or limit < 1:
        return []

    limit = min(limit, MAX_SEARCH_RESULTS)
    if _should_search_naver_krx(query):
        naver_results = _search_naver_krx(query, limit)
        if naver_results:
            return naver_results

    results = _search_krx(query, limit)
    remaining = limit - len(results)
    if remaining:
        results.extend(_search_us(query, remaining))
    return results
