"""
Redis-backed price cache. Cache key: price:{ticker}
Falls back to stock_fetcher on miss.
"""
import asyncio
import json
from decimal import Decimal
from datetime import date

import redis.asyncio as aioredis

from app.config import get_settings
from app.services.stock_fetcher import PriceResult, get_current_price

settings = get_settings()

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _cache_key(ticker: str) -> str:
    return f"price:{ticker.upper()}"


def _serialize(result: PriceResult) -> str:
    return json.dumps({
        "ticker": result.ticker,
        "market": result.market.value,
        "name": result.name,
        "currency": result.currency.value,
        "price": None if result.price is None else str(result.price),
        "price_date": result.price_date.isoformat(),
    })


def _deserialize(raw: str) -> PriceResult:
    from app.models.holding import Market, Currency
    data = json.loads(raw)
    return PriceResult(
        ticker=data["ticker"],
        market=Market(data["market"]),
        name=data["name"],
        currency=Currency(data["currency"]),
        price=None if data["price"] is None else Decimal(data["price"]),
        price_date=date.fromisoformat(data["price_date"]),
    )


async def get_price(ticker: str) -> PriceResult:
    """Get price from cache; fetch and cache on miss."""
    r = get_redis()
    key = _cache_key(ticker)
    raw = await r.get(key)
    if raw:
        return _deserialize(raw)

    result = await asyncio.to_thread(get_current_price, ticker)
    await r.setex(key, settings.price_cache_ttl, _serialize(result))
    return result


async def invalidate(ticker: str) -> None:
    r = get_redis()
    await r.delete(_cache_key(ticker))
