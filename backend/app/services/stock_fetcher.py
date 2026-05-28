"""
Stock data fetcher wrapping pykrx (KRX) and yfinance (US).

Market detection:
  - 6-digit numeric string  →  KRX
  - anything else            →  US (yfinance)
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf
from pykrx import stock as krx

from app.models.holding import Currency, Market


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


# ---------------------------------------------------------------------------
# KRX helpers
# ---------------------------------------------------------------------------

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
