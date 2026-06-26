import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.models.holding import Currency, Market, PrincipalFlow, TransactionType
from app.routers.holdings import _holding_performance
from app.services.lot_accounting import PortfolioScope

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _tx(*, tx_id, sgid, type_, qty, price, day, lot_id=None, allocations=()):
    return SimpleNamespace(
        id=tx_id, source_group_id=sgid, type=type_,
        quantity=Decimal(qty), price=Decimal(price),
        transaction_date=date(2026, 1, day), created_at=NOW,
        principal_flow=(PrincipalFlow.DEPOSIT if type_ == TransactionType.BUY else PrincipalFlow.WITHDRAW),
        requires_review=False,
        buy_lot=SimpleNamespace(id=lot_id) if lot_id else None,
        sell_allocations=list(allocations),
        transaction_labels=[],
    )


def _holding(transactions):
    return SimpleNamespace(
        id=uuid.uuid4(), ticker="005930", currency=Currency.KRW,
        market=Market.KRX, name="삼성전자", transactions=transactions,
    )


def test_source_scope_limits_principal_and_breakdown():
    sg_a, sg_b = uuid.uuid4(), uuid.uuid4()
    lot_a, lot_b = uuid.uuid4(), uuid.uuid4()
    holding = _holding([
        _tx(tx_id=uuid.uuid4(), sgid=sg_a, type_=TransactionType.BUY, qty="10", price="100", day=1, lot_id=lot_a),
        _tx(tx_id=uuid.uuid4(), sgid=sg_b, type_=TransactionType.BUY, qty="5", price="200", day=2, lot_id=lot_b),
    ])
    sources = [
        SimpleNamespace(id=sg_a, name="A", color="#111111"),
        SimpleNamespace(id=sg_b, name="B", color="#222222"),
    ]
    perf, breakdown = _holding_performance(
        holding, Decimal("150"), sources, scope=PortfolioScope("source", sg_a)
    )
    assert perf.total_invested_principal == Decimal("1000")  # only A: 10*100
    assert perf.remaining_cost_basis == Decimal("1000")
    assert perf.current_value == Decimal("1500")             # 10*150
    assert [b.source_group_id for b in breakdown] == [sg_a]


def test_all_scope_matches_legacy_default():
    sg_a = uuid.uuid4()
    lot_a = uuid.uuid4()
    holding = _holding([
        _tx(tx_id=uuid.uuid4(), sgid=sg_a, type_=TransactionType.BUY, qty="10", price="100", day=1, lot_id=lot_a),
    ])
    sources = [SimpleNamespace(id=sg_a, name="A", color="#111111")]
    perf, breakdown = _holding_performance(holding, Decimal("150"), sources)
    assert perf.total_invested_principal == Decimal("1000")
    assert len(breakdown) == 1
