from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.holding import Currency, Market
from app.services import price_cache
from app.services.price_cache import _deserialize, _serialize
from app.services.stock_fetcher import PriceResult


def _result(price):
    return PriceResult(
        ticker="DOW",
        market=Market.US,
        name="Dow Inc.",
        currency=Currency.USD,
        price=price,
        price_date=date(2026, 6, 17),
    )


def test_serialize_roundtrip_preserves_decimal_price():
    restored = _deserialize(_serialize(_result(Decimal("21.04"))))
    assert restored.price == Decimal("21.04")


def test_serialize_roundtrip_preserves_unavailable_price():
    restored = _deserialize(_serialize(_result(None)))
    assert restored.price is None
    assert restored.price_date == date(2026, 6, 17)


async def test_set_price_writes_serialized_quote_with_ttl(monkeypatch):
    redis = MagicMock()
    redis.setex = AsyncMock()
    monkeypatch.setattr(price_cache, "get_redis", lambda: redis)
    result = PriceResult(
        ticker="005930", market=Market.KRX, name="삼성전자",
        currency=Currency.KRW, price=Decimal("353500"), price_date=date(2026, 6, 22),
    )

    await price_cache.set_price("005930", result)

    redis.setex.assert_awaited_once()
    args = redis.setex.await_args.args
    assert args[0] == "price:005930"
    assert args[1] == price_cache.settings.price_cache_ttl
    assert "353500" in args[2] and "2026-06-22" in args[2]
