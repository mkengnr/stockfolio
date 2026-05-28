"""
Tests for holdings logic (recalculation helpers) — pure unit tests, no DB.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.holding import Holding, Transaction, TransactionType, Market, Currency
from app.routers.holdings import _recalculate_holding


def _make_tx(type_: TransactionType, qty: str, price: str) -> Transaction:
    tx = MagicMock(spec=Transaction)
    tx.type = type_
    tx.quantity = Decimal(qty)
    tx.price = Decimal(price)
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
        # qty: 10 - 5 = 5; avg_price still based on buy cost
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
        # avg_price keeps the buy weighted average; cost_basis = qty * avg_price = 0
        assert h.avg_price == Decimal("50000")

    def test_empty_transactions(self):
        h = _make_holding([])
        _recalculate_holding(h)
        assert h.quantity == Decimal("0")
        assert h.avg_price == Decimal("0")
