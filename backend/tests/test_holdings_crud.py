"""
Tests for holdings logic (recalculation helpers) — pure unit tests, no DB.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.models.holding import Holding, Transaction, TransactionType, Market, Currency
from app.routers.holdings import _recalculate_holding
from app.schemas.holding import HoldingCreateIn, TransactionIn


def _make_tx(type_: TransactionType, qty: str, price: str) -> Transaction:
    tx = MagicMock(spec=Transaction)
    tx.type = type_
    tx.quantity = Decimal(qty)
    tx.price = Decimal(price)
    tx.transaction_date = date(2024, 1, 1)
    return tx


def _make_holding(transactions: list[Transaction]) -> Holding:
    h = MagicMock(spec=Holding)
    h.transactions = transactions
    h.quantity = Decimal(0)
    h.avg_price = Decimal(0)
    return h


class TestRecalculateHolding:
    def test_single_buy(self):
        h = _make_holding([_make_tx(TransactionType.BUY, "10", "50000")])
        _recalculate_holding(h)
        assert h.quantity == Decimal("10")
        assert h.avg_price == Decimal("50000")

    def test_two_buys_weighted_average(self):
        txs = [
            _make_tx(TransactionType.BUY, "10", "50000"),
            _make_tx(TransactionType.BUY, "10", "60000"),
        ]
        h = _make_holding(txs)
        _recalculate_holding(h)
        assert h.quantity == Decimal("20")
        assert h.avg_price == Decimal("55000")

    def test_buy_then_partial_sell(self):
        txs = [
            _make_tx(TransactionType.BUY, "10", "50000"),
            _make_tx(TransactionType.SELL, "5", "55000"),
        ]
        h = _make_holding(txs)
        _recalculate_holding(h)
        # qty: 10 - 5 = 5; moving-average cost is unchanged by a partial sell
        assert h.quantity == Decimal("5")
        assert h.avg_price == Decimal("50000")

    def test_full_sell_quantity_is_zero(self):
        txs = [
            _make_tx(TransactionType.BUY, "10", "50000"),
            _make_tx(TransactionType.SELL, "10", "60000"),
        ]
        h = _make_holding(txs)
        _recalculate_holding(h)
        assert h.quantity == Decimal("0")
        assert h.avg_price == Decimal("0")

    def test_empty_transactions(self):
        h = _make_holding([])
        _recalculate_holding(h)
        assert h.quantity == Decimal("0")
        assert h.avg_price == Decimal("0")

    def test_full_sell_then_rebuy_resets_average(self):
        txs = [
            _make_tx(TransactionType.BUY, "10", "50000"),
            _make_tx(TransactionType.SELL, "10", "60000"),
            _make_tx(TransactionType.BUY, "5", "70000"),
        ]
        h = _make_holding(txs)
        _recalculate_holding(h)
        assert h.quantity == Decimal("5")
        assert h.avg_price == Decimal("70000")

    def test_rejects_oversell(self):
        h = _make_holding([
            _make_tx(TransactionType.BUY, "10", "50000"),
            _make_tx(TransactionType.SELL, "11", "60000"),
        ])
        with pytest.raises(ValueError, match="exceeds"):
            _recalculate_holding(h)


class TestTransactionValidation:
    @pytest.mark.parametrize("quantity", ["0", "-1"])
    def test_transaction_rejects_non_positive_quantity(self, quantity: str):
        with pytest.raises(ValidationError):
            TransactionIn(
                type=TransactionType.BUY,
                quantity=quantity,
                price="50000",
                transaction_date=date(2024, 1, 1),
            )

    @pytest.mark.parametrize("price", ["0", "-1"])
    def test_holding_rejects_non_positive_price(self, price: str):
        with pytest.raises(ValidationError):
            HoldingCreateIn(
                ticker="005930",
                quantity="10",
                price=price,
                transaction_date=date(2024, 1, 1),
            )
