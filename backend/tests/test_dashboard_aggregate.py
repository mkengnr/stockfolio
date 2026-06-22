import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.group import RollupGroup, RollupGroupMember, SourceGroup
from app.models.holding import Currency, Market, PrincipalFlow, TransactionType
from app.routers import portfolio as portfolio_router
from app.routers.deps import get_current_user
from app.routers.portfolio import (
    build_dashboard_response,
    build_portfolio_dashboard_response,
    get_portfolio_dashboard,
    router,
)
from app.services.exchange_rate import ExchangeRate


NOW = datetime(2026, 6, 2, tzinfo=timezone.utc)
RATE = ExchangeRate(
    base="USD",
    quote="KRW",
    rate=Decimal("1300"),
    as_of=datetime(2026, 6, 4, tzinfo=timezone.utc),
)


class _Result:
    def __init__(self, *, many=None):
        self._many = list(many or [])

    def scalars(self):
        return self

    def all(self):
        return self._many


class _QueuedSession:
    def __init__(self):
        self.results = []

    def queue(self, *results):
        self.results.extend(results)

    async def execute(self, _query):
        assert self.results, "unexpected database query"
        return self.results.pop(0)


def _source(user_id, *, name, color="#6366f1", source_id=None):
    return SourceGroup(
        id=source_id or uuid.uuid4(),
        user_id=user_id,
        name=name,
        color=color,
        description=None,
        share_requires_auth=True,
        created_at=NOW,
    )


def _rollup(user_id, *sources, name="통합", color="#22c55e"):
    return RollupGroup(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        color=color,
        description=None,
        share_requires_auth=True,
        created_at=NOW,
        members=[RollupGroupMember(source_group_id=source.id) for source in sources],
    )


def _buy(
    holding_id,
    ticker,
    currency,
    *,
    source_group_id=None,
    quantity="1",
    price="100",
    tx_date=date(2026, 1, 1),
    principal_flow=PrincipalFlow.DEPOSIT,
):
    tx_id = uuid.uuid4()
    return SimpleNamespace(
        id=tx_id,
        holding_id=holding_id,
        type=TransactionType.BUY,
        quantity=Decimal(quantity),
        price=Decimal(price),
        transaction_date=tx_date,
        created_at=NOW,
        source_group_id=source_group_id,
        principal_flow=principal_flow,
        requires_review=False,
        buy_lot=SimpleNamespace(id=uuid.uuid4()),
        sell_allocations=[],
        transaction_labels=[],
    )


def _sell(
    holding_id,
    buy_transaction,
    *,
    source_group_id=None,
    quantity="1",
    price="120",
    tx_date=date(2026, 2, 1),
    principal_flow=PrincipalFlow.REINVEST,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        holding_id=holding_id,
        type=TransactionType.SELL,
        quantity=Decimal(quantity),
        price=Decimal(price),
        transaction_date=tx_date,
        created_at=NOW,
        source_group_id=source_group_id,
        principal_flow=principal_flow,
        requires_review=False,
        buy_lot=None,
        sell_allocations=[
            SimpleNamespace(
                buy_lot_id=buy_transaction.buy_lot.id,
                quantity=Decimal(quantity),
            )
        ],
        transaction_labels=[],
    )


def _holding(ticker, currency, *transactions, name=None, active=True, snapshots=()):
    market = Market.KRX if currency == Currency.KRW else Market.US
    return SimpleNamespace(
        id=transactions[0].holding_id,
        ticker=ticker,
        market=market,
        name=name or ticker,
        currency=currency,
        is_active=active,
        transactions=list(transactions),
        snapshots=list(snapshots),
    )


def _snapshot(snapshot_date, close_price):
    return SimpleNamespace(snapshot_date=snapshot_date, close_price=Decimal(close_price))


def test_krw_display_converts_usd_assets_and_includes_group_rows():
    user_id = uuid.uuid4()
    salary = _source(user_id, name="월급", color="#111111")
    family = _rollup(user_id, salary, name="가족", color="#222222")
    krw_holding_id = uuid.uuid4()
    usd_holding_id = uuid.uuid4()
    holdings = [
        _holding(
            "005930",
            Currency.KRW,
            _buy(krw_holding_id, "005930", Currency.KRW, quantity="2", price="1000"),
            name="삼성전자",
        ),
        _holding(
            "AAPL",
            Currency.USD,
            _buy(
                usd_holding_id,
                "AAPL",
                Currency.USD,
                source_group_id=salary.id,
                quantity="3",
                price="10",
            ),
            name="Apple",
        ),
    ]

    response = build_dashboard_response(
        holdings=holdings,
        source_groups=[salary],
        rollup_groups=[family],
        current_prices={"005930": Decimal("1200"), "AAPL": Decimal("12")},
        display_currency="KRW",
        exchange_rate=RATE,
    )

    assert response.display_currency == "KRW"
    assert response.summary.total_invested_principal == Decimal("41000")
    assert response.summary.total_cost_basis == Decimal("41000")
    assert response.summary.total_current_value == Decimal("49200")
    assert response.summary.total_profit_loss == Decimal("8200")
    assert response.summary.total_profit_loss_pct == Decimal("20.0")
    assert [(group.kind, group.name) for group in response.groups] == [
        ("source", "월급"),
        ("combined", "가족"),
        ("unclassified", "미분류"),
    ]
    assert response.groups[0].summary.total_current_value == Decimal("46800")
    assert response.groups[1].summary.total_current_value == Decimal("46800")
    assert response.groups[2].summary.total_current_value == Decimal("2400")
    assert response.groups[0].source_group_ids == [salary.id]
    assert response.groups[1].source_group_ids == [salary.id]
    assert response.groups[2].source_group_ids == []


def test_usd_display_includes_only_usd_assets():
    user_id = uuid.uuid4()
    salary = _source(user_id, name="월급")
    krw_holding_id = uuid.uuid4()
    usd_holding_id = uuid.uuid4()
    holdings = [
        _holding(
            "005930",
            Currency.KRW,
            _buy(krw_holding_id, "005930", Currency.KRW, quantity="2", price="1000"),
        ),
        _holding(
            "AAPL",
            Currency.USD,
            _buy(
                usd_holding_id,
                "AAPL",
                Currency.USD,
                source_group_id=salary.id,
                quantity="3",
                price="10",
            ),
        ),
    ]

    response = build_dashboard_response(
        holdings=holdings,
        source_groups=[salary],
        rollup_groups=[],
        current_prices={"005930": Decimal("1200"), "AAPL": Decimal("12")},
        display_currency="USD",
        exchange_rate=RATE,
    )

    assert response.summary.total_invested_principal == Decimal("30")
    assert response.summary.total_cost_basis == Decimal("30")
    assert response.summary.total_current_value == Decimal("36")
    assert [holding.ticker for holding in response.holdings] == ["AAPL"]
    assert [group.name for group in response.groups] == ["월급"]


def test_krw_display_without_rate_nulls_usd_only_summary():
    user_id = uuid.uuid4()
    salary = _source(user_id, name="월급")
    holding_id = uuid.uuid4()
    holding = _holding(
        "AAPL",
        Currency.USD,
        _buy(
            holding_id,
            "AAPL",
            Currency.USD,
            source_group_id=salary.id,
            quantity="3",
            price="10",
        ),
    )

    response = build_dashboard_response(
        holdings=[holding],
        source_groups=[salary],
        rollup_groups=[],
        current_prices={"AAPL": Decimal("12")},
        display_currency="KRW",
        exchange_rate=None,
    )

    assert response.summary.total_invested_principal is None
    assert response.summary.total_cost_basis is None
    assert response.summary.total_current_value is None
    assert response.summary.total_profit_loss is None
    assert "USD/KRW exchange rate unavailable; USD values are omitted" in response.warnings


def test_krw_display_without_rate_keeps_krw_values_for_mixed_summary():
    user_id = uuid.uuid4()
    krw_holding_id = uuid.uuid4()
    usd_holding_id = uuid.uuid4()
    holdings = [
        _holding(
            "005930",
            Currency.KRW,
            _buy(krw_holding_id, "005930", Currency.KRW, quantity="2", price="1000"),
        ),
        _holding(
            "AAPL",
            Currency.USD,
            _buy(usd_holding_id, "AAPL", Currency.USD, quantity="3", price="10"),
        ),
    ]

    response = build_dashboard_response(
        holdings=holdings,
        source_groups=[],
        rollup_groups=[],
        current_prices={"005930": Decimal("1200"), "AAPL": Decimal("12")},
        display_currency="KRW",
        exchange_rate=None,
    )

    assert response.summary.total_invested_principal == Decimal("2000")
    assert response.summary.total_cost_basis == Decimal("2000")
    assert response.summary.total_current_value == Decimal("2400")
    assert response.summary.total_profit_loss == Decimal("400")
    assert response.summary.total_profit_loss_pct == Decimal("20.0")
    assert "USD/KRW exchange rate unavailable; USD values are omitted" in response.warnings


def test_holding_group_badges_use_remaining_lot_source_groups_only():
    user_id = uuid.uuid4()
    salary = _source(user_id, name="월급", color="#111111")
    bonus = _source(user_id, name="보너스", color="#222222")
    family = _rollup(user_id, salary, bonus, name="가족")
    holding_id = uuid.uuid4()
    sold_salary_buy = _buy(
        holding_id,
        "AAPL",
        Currency.USD,
        source_group_id=salary.id,
        quantity="2",
        price="10",
    )
    remaining_bonus_buy = _buy(
        holding_id,
        "AAPL",
        Currency.USD,
        source_group_id=bonus.id,
        quantity="3",
        price="10",
        tx_date=date(2026, 1, 2),
    )
    unclassified_buy = _buy(
        holding_id,
        "AAPL",
        Currency.USD,
        quantity="1",
        price="10",
        tx_date=date(2026, 1, 3),
    )
    holding = _holding(
        "AAPL",
        Currency.USD,
        sold_salary_buy,
        remaining_bonus_buy,
        unclassified_buy,
        _sell(
            holding_id,
            sold_salary_buy,
            source_group_id=salary.id,
            quantity="2",
            price="11",
        ),
    )

    response = build_dashboard_response(
        holdings=[holding],
        source_groups=[salary, bonus],
        rollup_groups=[family],
        current_prices={"AAPL": Decimal("12")},
        display_currency="USD",
        exchange_rate=RATE,
    )

    assert [(badge.name, badge.remaining_quantity) for badge in response.holdings[0].groups] == [
        ("보너스", Decimal("3")),
        ("미분류", Decimal("1")),
    ]
    groups = {group.name: group for group in response.groups}
    assert groups["보너스"].holdings[0].quantity == Decimal("3")
    assert groups["보너스"].holdings[0].remaining_cost_basis == Decimal("30")
    assert groups["보너스"].holdings[0].current_value == Decimal("36")
    assert groups["보너스"].holdings[0].unrealized_profit_loss == Decimal("6")
    assert groups["가족"].holdings[0].quantity == Decimal("3")
    assert groups["미분류"].holdings[0].quantity == Decimal("1")


def test_holding_remaining_cost_basis_is_null_when_conversion_fails():
    user_id = uuid.uuid4()
    holding_id = uuid.uuid4()
    holding = _holding(
        "AAPL",
        Currency.USD,
        _buy(holding_id, "AAPL", Currency.USD, quantity="2", price="10"),
    )

    response = build_dashboard_response(
        holdings=[holding],
        source_groups=[],
        rollup_groups=[],
        current_prices={"AAPL": Decimal("12")},
        display_currency="KRW",
        exchange_rate=None,
    )

    assert response.holdings[0].remaining_cost_basis is None


def test_dashboard_history_includes_inactive_holding_snapshots():
    active_holding_id = uuid.uuid4()
    inactive_holding_id = uuid.uuid4()
    holdings = [
        _holding(
            "005930",
            Currency.KRW,
            _buy(active_holding_id, "005930", Currency.KRW, quantity="1", price="1000"),
            snapshots=[_snapshot(date(2026, 1, 2), "1100")],
        ),
        _holding(
            "000660",
            Currency.KRW,
            _buy(inactive_holding_id, "000660", Currency.KRW, quantity="2", price="500"),
            active=False,
            snapshots=[_snapshot(date(2026, 1, 3), "600")],
        ),
    ]

    response = build_dashboard_response(
        holdings=holdings,
        source_groups=[],
        rollup_groups=[],
        current_prices={"005930": Decimal("1200")},
        display_currency="KRW",
        exchange_rate=None,
    )

    total_rows = [row for row in response.history.rows if row.group_kind == "total"]
    assert [row.snapshot_date for row in total_rows] == [
        date(2026, 1, 2),
        date(2026, 1, 3),
    ]
    assert total_rows[1].total_value == Decimal("2300")
    assert [holding.ticker for holding in response.holdings] == ["005930"]


def test_dashboard_history_keeps_closed_source_group_for_composition():
    user_id = uuid.uuid4()
    source = _source(user_id, name="과거 계좌")
    holding_id = uuid.uuid4()
    buy = _buy(
        holding_id,
        "005930",
        Currency.KRW,
        source_group_id=source.id,
        quantity="1",
        price="100",
        tx_date=date(2026, 1, 1),
    )
    holding = _holding(
        "005930",
        Currency.KRW,
        buy,
        _sell(
            holding_id,
            buy,
            source_group_id=source.id,
            quantity="1",
            price="100",
            tx_date=date(2026, 2, 1),
            principal_flow=PrincipalFlow.WITHDRAW,
        ),
        snapshots=[
            _snapshot(date(2026, 1, 2), "100"),
            _snapshot(date(2026, 2, 2), "100"),
        ],
    )

    response = build_dashboard_response(
        holdings=[holding],
        source_groups=[source],
        rollup_groups=[],
        current_prices={"005930": Decimal("100")},
        display_currency="KRW",
        exchange_rate=None,
    )

    assert response.groups == []
    source_rows = [row for row in response.history.rows if row.group_kind == "source"]
    assert source_rows[0].snapshot_date == date(2026, 1, 2)
    assert source_rows[0].total_value == Decimal("100")


def test_dashboard_summary_separates_unrealized_and_total_profit_and_daily_change():
    holding_id = uuid.uuid4()
    buy = _buy(
        holding_id,
        "005930",
        Currency.KRW,
        quantity="2",
        price="1000",
        tx_date=date(2026, 1, 1),
    )
    sell = _sell(
        holding_id,
        buy,
        quantity="1",
        price="1300",
        tx_date=date(2026, 2, 1),
        principal_flow=PrincipalFlow.WITHDRAW,
    )
    holding = _holding(
        "005930",
        Currency.KRW,
        buy,
        sell,
        snapshots=[_snapshot(date(2026, 6, 4), "1100")],
    )

    response = build_dashboard_response(
        holdings=[holding],
        source_groups=[],
        rollup_groups=[],
        current_prices={"005930": Decimal("1500")},
        display_currency="KRW",
        exchange_rate=None,
    )

    assert response.summary.total_invested_principal == Decimal("700")
    assert response.summary.total_cost_basis == Decimal("1000")
    assert response.summary.total_current_value == Decimal("1500")
    assert response.summary.total_unrealized_profit_loss == Decimal("500")
    assert response.summary.total_unrealized_profit_loss_pct == Decimal("50.0")
    # 총손익 = 평가손익(1500-1000) + 실현손익(1 × (1300-1000)); 총손익률은 투자원금 대비
    assert response.summary.total_profit_loss == Decimal("800")
    assert response.summary.total_profit_loss_pct == Decimal("114.2857142857142857142857143")
    assert response.summary.total_current_value_change == Decimal("400")


def test_dashboard_daily_change_uses_previous_trading_day_not_today_snapshot(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 5)

    monkeypatch.setattr(portfolio_router, "date", FixedDate)

    holding_id = uuid.uuid4()
    holding = _holding(
        "005930",
        Currency.KRW,
        _buy(
            holding_id,
            "005930",
            Currency.KRW,
            quantity="1",
            price="1000",
            tx_date=date(2026, 1, 1),
        ),
        snapshots=[
            _snapshot(date(2026, 6, 4), "1100"),
            _snapshot(date(2026, 6, 5), "1500"),
        ],
    )

    response = build_dashboard_response(
        holdings=[holding],
        source_groups=[],
        rollup_groups=[],
        current_prices={"005930": Decimal("1500")},
        display_currency="KRW",
        exchange_rate=None,
    )

    assert response.summary.total_current_value == Decimal("1500")
    assert response.summary.total_current_value_change == Decimal("400")
    # 전일대비율 = 400 / 전일 평가금액(1100) × 100
    assert round(response.summary.total_current_value_change_pct, 2) == Decimal("36.36")


def test_dashboard_daily_change_uses_current_price_date_as_reference_day(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 6)

    monkeypatch.setattr(portfolio_router, "date", FixedDate)

    holding_id = uuid.uuid4()
    holding = _holding(
        "005930",
        Currency.KRW,
        _buy(
            holding_id,
            "005930",
            Currency.KRW,
            quantity="1",
            price="1000",
            tx_date=date(2026, 1, 1),
        ),
        snapshots=[
            _snapshot(date(2026, 6, 4), "1100"),
            _snapshot(date(2026, 6, 5), "1500"),
        ],
    )

    response = build_dashboard_response(
        holdings=[holding],
        source_groups=[],
        rollup_groups=[],
        current_prices={"005930": Decimal("1500")},
        current_price_dates={"005930": date(2026, 6, 5)},
        display_currency="KRW",
        exchange_rate=None,
    )

    assert response.current_price_as_of == date(2026, 6, 5)
    assert response.comparison_as_of == date(2026, 6, 4)
    assert response.summary.total_current_value == Decimal("1500")
    assert response.summary.total_current_value_change == Decimal("400")
    assert response.holdings[0].current_value_change == Decimal("400")


def test_dashboard_daily_change_is_per_holding_own_trading_day_and_sums_to_summary():
    # Mixed trading days: one ticker's latest price is 6/22, another's is 6/18
    # (e.g. KRX vs a market closed 6/19). Each holding's 전일대비 must compare to
    # ITS OWN previous trading day, and the summary must equal the sum of holdings.
    a_id = uuid.uuid4()
    holding_a = _holding(
        "005930",
        Currency.KRW,
        _buy(a_id, "005930", Currency.KRW, quantity="1", price="1000", tx_date=date(2026, 1, 1)),
        snapshots=[_snapshot(date(2026, 6, 17), "1000"), _snapshot(date(2026, 6, 19), "1100")],
    )
    b_id = uuid.uuid4()
    holding_b = _holding(
        "000660",
        Currency.KRW,
        _buy(b_id, "000660", Currency.KRW, quantity="1", price="2000", tx_date=date(2026, 1, 1)),
        snapshots=[_snapshot(date(2026, 6, 17), "2000")],
    )

    response = build_dashboard_response(
        holdings=[holding_a, holding_b],
        source_groups=[],
        rollup_groups=[],
        current_prices={"005930": Decimal("1200"), "000660": Decimal("2100")},
        current_price_dates={"005930": date(2026, 6, 22), "000660": date(2026, 6, 18)},
        display_currency="KRW",
        exchange_rate=None,
    )

    rows = {row.ticker: row for row in response.holdings}
    # A compares 6/22 price vs its own previous trading day 6/19 (1100): +100
    assert rows["005930"].current_value_change == Decimal("100")
    # B compares 6/18 price vs 6/17 (2000): +100
    assert rows["000660"].current_value_change == Decimal("100")
    # Summary 전일대비 equals the sum of per-holding changes
    assert response.summary.total_current_value_change == Decimal("200")


def test_dashboard_exposes_per_market_price_and_comparison_dates():
    krx_id = uuid.uuid4()
    krx = _holding(
        "005930",
        Currency.KRW,
        _buy(krx_id, "005930", Currency.KRW, quantity="1", price="1000", tx_date=date(2026, 1, 1)),
        snapshots=[_snapshot(date(2026, 6, 17), "1000"), _snapshot(date(2026, 6, 19), "1100")],
    )
    us_id = uuid.uuid4()
    us = _holding(
        "AAPL",
        Currency.USD,
        _buy(us_id, "AAPL", Currency.USD, quantity="1", price="100", tx_date=date(2026, 1, 1)),
        snapshots=[_snapshot(date(2026, 6, 16), "105"), _snapshot(date(2026, 6, 17), "110")],
    )

    response = build_dashboard_response(
        holdings=[krx, us],
        source_groups=[],
        rollup_groups=[],
        current_prices={"005930": Decimal("1200"), "AAPL": Decimal("120")},
        current_price_dates={"005930": date(2026, 6, 22), "AAPL": date(2026, 6, 18)},
        display_currency="KRW",
        exchange_rate=RATE,
    )

    assert response.price_dates_by_market == {"KRX": date(2026, 6, 22), "US": date(2026, 6, 18)}
    assert response.comparison_dates_by_market == {"KRX": date(2026, 6, 19), "US": date(2026, 6, 17)}


def test_krw_history_without_rate_nulls_usd_only_values():
    holding_id = uuid.uuid4()
    holding = _holding(
        "AAPL",
        Currency.USD,
        _buy(holding_id, "AAPL", Currency.USD, quantity="2", price="10"),
        snapshots=[_snapshot(date(2026, 1, 2), "12")],
    )

    response = build_dashboard_response(
        holdings=[holding],
        source_groups=[],
        rollup_groups=[],
        current_prices={"AAPL": Decimal("12")},
        display_currency="KRW",
        exchange_rate=None,
    )

    total_rows = [row for row in response.history.rows if row.group_kind == "total"]
    assert total_rows[0].total_value is None
    assert total_rows[0].total_invested_principal is None
    assert "USD/KRW exchange rate unavailable; USD values are omitted" in response.warnings


def test_krw_history_without_rate_keeps_krw_values_for_mixed_history():
    krw_holding_id = uuid.uuid4()
    usd_holding_id = uuid.uuid4()
    holdings = [
        _holding(
            "005930",
            Currency.KRW,
            _buy(krw_holding_id, "005930", Currency.KRW, quantity="1", price="1000"),
            snapshots=[_snapshot(date(2026, 1, 2), "1100")],
        ),
        _holding(
            "AAPL",
            Currency.USD,
            _buy(usd_holding_id, "AAPL", Currency.USD, quantity="2", price="10"),
            snapshots=[_snapshot(date(2026, 1, 2), "12")],
        ),
    ]

    response = build_dashboard_response(
        holdings=holdings,
        source_groups=[],
        rollup_groups=[],
        current_prices={"005930": Decimal("1100"), "AAPL": Decimal("12")},
        display_currency="KRW",
        exchange_rate=None,
    )

    total_rows = [row for row in response.history.rows if row.group_kind == "total"]
    assert total_rows[0].total_value == Decimal("1100")
    assert total_rows[0].total_invested_principal == Decimal("1000")
    assert total_rows[0].total_profit_loss == Decimal("100")
    assert "USD/KRW exchange rate unavailable; USD values are omitted" in response.warnings


@pytest.mark.asyncio
async def test_dashboard_rate_lookup_runs_in_thread_for_inactive_usd_history(monkeypatch):
    user_id = uuid.uuid4()
    holding_id = uuid.uuid4()
    holding = _holding(
        "AAPL",
        Currency.USD,
        _buy(holding_id, "AAPL", Currency.USD),
        active=False,
        snapshots=[_snapshot(date(2026, 1, 2), "12")],
    )
    calls = []

    async def _load_scoped_holdings(_db, _user_id, *, include_inactive=False):
        return [holding]

    async def _load_dashboard_groups(_db, _user_id):
        return [], []

    async def _fetch_current_prices(_tickers):
        assert _tickers == set()
        return {}

    def _get_usd_krw_rate():
        raise AssertionError("get_usd_krw_rate should be called through to_thread")

    async def _to_thread(func, *args, **kwargs):
        calls.append(func)
        return RATE

    monkeypatch.setattr(portfolio_router, "_load_scoped_holdings", _load_scoped_holdings)
    monkeypatch.setattr(portfolio_router, "_load_dashboard_groups", _load_dashboard_groups)
    monkeypatch.setattr(portfolio_router, "_fetch_current_prices", _fetch_current_prices)
    monkeypatch.setattr(portfolio_router, "get_usd_krw_rate", _get_usd_krw_rate)
    monkeypatch.setattr(portfolio_router.asyncio, "to_thread", _to_thread)

    response = await build_portfolio_dashboard_response(
        _QueuedSession(),
        user_id,
        display_currency="KRW",
    )

    assert calls == [_get_usd_krw_rate]
    assert response.exchange_rate.rate == Decimal("1300")
    assert response.holdings == []
    assert response.history.rows[0].total_value == Decimal("15600")


@pytest.mark.asyncio
async def test_dashboard_recovers_missing_recent_comparison_snapshot_and_reloads_holdings(monkeypatch):
    user_id = uuid.uuid4()
    holding_id = uuid.uuid4()
    newer_quote_holding_id = uuid.uuid4()
    stale_holding = _holding(
        "005930",
        Currency.KRW,
        _buy(holding_id, "005930", Currency.KRW),
        snapshots=[_snapshot(date(2026, 6, 5), "100")],
    )
    newer_quote_stale_holding = _holding(
        "000660",
        Currency.KRW,
        _buy(newer_quote_holding_id, "000660", Currency.KRW),
        snapshots=[_snapshot(date(2026, 6, 5), "200")],
    )
    recovered_holding = _holding(
        "005930",
        Currency.KRW,
        _buy(holding_id, "005930", Currency.KRW),
        snapshots=[
            _snapshot(date(2026, 6, 5), "100"),
            _snapshot(date(2026, 6, 8), "110"),
        ],
    )
    newer_quote_recovered_holding = _holding(
        "000660",
        Currency.KRW,
        _buy(newer_quote_holding_id, "000660", Currency.KRW),
        snapshots=[
            _snapshot(date(2026, 6, 5), "200"),
            _snapshot(date(2026, 6, 8), "210"),
        ],
    )
    loaded_holdings = [
        [stale_holding, newer_quote_stale_holding],
        [recovered_holding, newer_quote_recovered_holding],
    ]
    db = SimpleNamespace(commit=AsyncMock())
    recover = AsyncMock(return_value=1)

    async def _load_scoped_holdings(_db, _user_id, *, include_inactive=False):
        return loaded_holdings.pop(0)

    async def _load_dashboard_groups(_db, _user_id):
        return [], []

    async def _fetch_current_price_quotes(_tickers):
        return {
            "005930": portfolio_router.CurrentPriceQuote(
                price=Decimal("120"),
                price_date=date(2026, 6, 9),
            ),
            "000660": portfolio_router.CurrentPriceQuote(
                price=Decimal("220"),
                price_date=date(2026, 6, 10),
            ),
        }

    monkeypatch.setattr(portfolio_router, "_load_scoped_holdings", _load_scoped_holdings)
    monkeypatch.setattr(portfolio_router, "_load_dashboard_groups", _load_dashboard_groups)
    monkeypatch.setattr(portfolio_router, "_fetch_current_price_quotes", _fetch_current_price_quotes)
    monkeypatch.setattr(portfolio_router, "backfill_recent_comparison_snapshots", recover)

    response = await build_portfolio_dashboard_response(db, user_id)

    assert recover.await_count == 2
    assert recover.await_args_list[0].args == (db, stale_holding)
    assert recover.await_args_list[1].args == (db, newer_quote_stale_holding)
    # Each holding uses its own quote.price_date for recovery (per-holding, not global).
    assert recover.await_args_list[0].kwargs == {"current_price_date": date(2026, 6, 9)}
    assert recover.await_args_list[1].kwargs == {"current_price_date": date(2026, 6, 10)}
    db.commit.assert_awaited_once()
    assert response.comparison_as_of == date(2026, 6, 8)


@pytest.mark.asyncio
async def test_dashboard_warns_when_recent_comparison_snapshot_recovery_fails(monkeypatch):
    user_id = uuid.uuid4()
    holding_id = uuid.uuid4()
    holding = _holding(
        "005930",
        Currency.KRW,
        _buy(holding_id, "005930", Currency.KRW),
        snapshots=[_snapshot(date(2026, 6, 5), "100")],
    )
    db = SimpleNamespace(commit=AsyncMock())

    async def _load_scoped_holdings(_db, _user_id, *, include_inactive=False):
        return [holding]

    async def _load_dashboard_groups(_db, _user_id):
        return [], []

    async def _fetch_current_price_quotes(_tickers):
        return {
            "005930": portfolio_router.CurrentPriceQuote(
                price=Decimal("120"),
                price_date=date(2026, 6, 9),
            )
        }

    async def _fail_recovery(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(portfolio_router, "_load_scoped_holdings", _load_scoped_holdings)
    monkeypatch.setattr(portfolio_router, "_load_dashboard_groups", _load_dashboard_groups)
    monkeypatch.setattr(portfolio_router, "_fetch_current_price_quotes", _fetch_current_price_quotes)
    monkeypatch.setattr(portfolio_router, "backfill_recent_comparison_snapshots", _fail_recovery)

    response = await build_portfolio_dashboard_response(db, user_id)

    assert response.comparison_as_of == date(2026, 6, 5)
    assert any("005930 직전 거래일 스냅샷 복구 실패" in warning for warning in response.warnings)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_dashboard_reloads_after_concurrent_snapshot_recovery_commit(monkeypatch):
    user_id = uuid.uuid4()
    holding_id = uuid.uuid4()
    stale_holding = _holding(
        "005930",
        Currency.KRW,
        _buy(holding_id, "005930", Currency.KRW),
        snapshots=[_snapshot(date(2026, 6, 5), "100")],
    )
    recovered_holding = _holding(
        "005930",
        Currency.KRW,
        _buy(holding_id, "005930", Currency.KRW),
        snapshots=[
            _snapshot(date(2026, 6, 5), "100"),
            _snapshot(date(2026, 6, 8), "110"),
        ],
    )
    loaded_holdings = [[stale_holding], [recovered_holding]]
    db = SimpleNamespace(
        commit=AsyncMock(
            side_effect=IntegrityError("snapshot_date unique constraint", {}, Exception())
        ),
        rollback=AsyncMock(),
    )

    async def _load_scoped_holdings(_db, _user_id, *, include_inactive=False):
        return loaded_holdings.pop(0)

    async def _load_dashboard_groups(_db, _user_id):
        return [], []

    async def _fetch_current_price_quotes(_tickers):
        return {
            "005930": portfolio_router.CurrentPriceQuote(
                price=Decimal("120"),
                price_date=date(2026, 6, 9),
            )
        }

    monkeypatch.setattr(portfolio_router, "_load_scoped_holdings", _load_scoped_holdings)
    monkeypatch.setattr(portfolio_router, "_load_dashboard_groups", _load_dashboard_groups)
    monkeypatch.setattr(portfolio_router, "_fetch_current_price_quotes", _fetch_current_price_quotes)
    monkeypatch.setattr(
        portfolio_router,
        "backfill_recent_comparison_snapshots",
        AsyncMock(return_value=1),
    )

    response = await build_portfolio_dashboard_response(db, user_id)

    db.rollback.assert_awaited_once()
    assert response.comparison_as_of == date(2026, 6, 8)


@pytest.mark.asyncio
async def test_dashboard_skips_recovery_when_friday_snapshot_precedes_monday_quote(monkeypatch):
    user_id = uuid.uuid4()
    holding_id = uuid.uuid4()
    holding = _holding(
        "005930",
        Currency.KRW,
        _buy(holding_id, "005930", Currency.KRW),
        snapshots=[_snapshot(date(2026, 6, 5), "100")],
    )
    db = SimpleNamespace(commit=AsyncMock())
    recover = AsyncMock(return_value=0)

    async def _load_scoped_holdings(_db, _user_id, *, include_inactive=False):
        return [holding]

    async def _load_dashboard_groups(_db, _user_id):
        return [], []

    async def _fetch_current_price_quotes(_tickers):
        return {
            "005930": portfolio_router.CurrentPriceQuote(
                price=Decimal("120"),
                price_date=date(2026, 6, 8),
            )
        }

    monkeypatch.setattr(portfolio_router, "_load_scoped_holdings", _load_scoped_holdings)
    monkeypatch.setattr(portfolio_router, "_load_dashboard_groups", _load_dashboard_groups)
    monkeypatch.setattr(portfolio_router, "_fetch_current_price_quotes", _fetch_current_price_quotes)
    monkeypatch.setattr(portfolio_router, "backfill_recent_comparison_snapshots", recover)

    response = await build_portfolio_dashboard_response(db, user_id)

    recover.assert_not_awaited()
    assert response.comparison_as_of == date(2026, 6, 5)


@pytest.mark.asyncio
async def test_dashboard_endpoint_returns_authenticated_aggregate(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4())
    source = _source(user.id, name="월급")
    holding_id = uuid.uuid4()
    holding = _holding(
        "AAPL",
        Currency.USD,
        _buy(holding_id, "AAPL", Currency.USD, source_group_id=source.id),
        snapshots=[_snapshot(date(2026, 1, 2), "11")],
    )
    db = _QueuedSession()
    db.queue(_Result(many=[holding]), _Result(many=[source]), _Result(many=[]))

    async def _fetch_current_price_quotes(tickers):
        assert tickers == {"AAPL"}
        return {
            "AAPL": portfolio_router.CurrentPriceQuote(
                price=Decimal("12"),
                price_date=date(2026, 1, 3),
            )
        }

    monkeypatch.setattr(portfolio_router, "_fetch_current_price_quotes", _fetch_current_price_quotes)
    monkeypatch.setattr(portfolio_router, "get_usd_krw_rate", lambda: RATE)

    response = await get_portfolio_dashboard(current_user=user, db=db)

    assert response.display_currency == "KRW"
    assert response.current_price_as_of == date(2026, 1, 3)
    assert response.comparison_as_of == date(2026, 1, 2)
    assert response.summary.total_current_value == Decimal("15600")
    assert response.groups[0].name == "월급"
    assert response.holdings[0].ticker == "AAPL"
    assert response.history.rows[0].group_kind == "total"


def test_dashboard_endpoint_requires_authentication():
    app = FastAPI()
    app.include_router(router)

    async def _unauthenticated_user():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    async def _unused_db():
        yield _QueuedSession()

    app.dependency_overrides[get_current_user] = _unauthenticated_user
    app.dependency_overrides[get_db] = _unused_db

    response = TestClient(app).get("/api/portfolio/dashboard")

    assert response.status_code == 401


def test_comparison_recovery_uses_per_holding_price_date():
    from types import SimpleNamespace
    from app.routers.portfolio import _holdings_needing_comparison_recovery, CurrentPriceQuote
    krx = SimpleNamespace(ticker="005930", snapshots=[SimpleNamespace(snapshot_date=date(2026, 6, 19))])
    us = SimpleNamespace(ticker="AAPL", snapshots=[SimpleNamespace(snapshot_date=date(2026, 6, 17))])
    quotes = {
        "005930": CurrentPriceQuote(price=Decimal("1"), price_date=date(2026, 6, 22)),
        "AAPL": CurrentPriceQuote(price=Decimal("1"), price_date=date(2026, 6, 18)),
    }
    needing = _holdings_needing_comparison_recovery([krx, us], quotes)
    # KRX는 6/19 스냅샷 있고 직전영업일(6/19)≥기준 → 복구 불필요. US는 6/17만 있어 6/18 직전(6/17)≥기준 → 불필요.
    assert needing == []
    # KRX 스냅샷을 6/17로 낮추면 6/22 기준 직전영업일(6/19) 미달 → 복구 필요(기준일=6/22)
    krx.snapshots = [SimpleNamespace(snapshot_date=date(2026, 6, 17))]
    needing2 = _holdings_needing_comparison_recovery([krx, us], quotes)
    assert (krx, date(2026, 6, 22)) in needing2
