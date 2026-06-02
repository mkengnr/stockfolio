from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.holding import Currency
from app.routers.tags import _compute_summary


def _holding(currency: Currency, ticker: str, quantity: str, avg_price: str):
    return SimpleNamespace(
        is_active=True,
        currency=currency,
        ticker=ticker,
        quantity=Decimal(quantity),
        avg_price=Decimal(avg_price),
    )


@pytest.mark.asyncio
async def test_compute_summary_keeps_currencies_separate():
    holdings = [
        _holding(Currency.KRW, "005930", "10", "70000"),
        _holding(Currency.USD, "AAPL", "2", "100"),
    ]

    async def get_price(ticker: str):
        return SimpleNamespace(price=Decimal("75000" if ticker == "005930" else "120"))

    with patch("app.routers.tags.get_price", new=AsyncMock(side_effect=get_price)):
        summary = await _compute_summary(holdings)

    assert summary.holding_count == 2
    assert summary.currencies[Currency.KRW].total_cost_basis == Decimal("700000")
    assert summary.currencies[Currency.KRW].total_current_value == Decimal("750000")
    assert summary.currencies[Currency.USD].total_cost_basis == Decimal("200")
    assert summary.currencies[Currency.USD].total_current_value == Decimal("240")
