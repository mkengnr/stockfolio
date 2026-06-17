from datetime import date
from decimal import Decimal

from app.models.holding import Currency, Market
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
