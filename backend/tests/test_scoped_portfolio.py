import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from app.models.group import Label, RollupGroup, RollupGroupMember, SourceGroup
from app.models.holding import Currency, PrincipalFlow, TransactionType
from app.routers import portfolio as portfolio_router
from app.routers.portfolio import (
    _build_scoped_dashboard_payload,
    _build_scoped_history,
    _scoped_holdings_query,
    build_scoped_portfolio_dashboard,
    build_scoped_portfolio_history,
    get_portfolio_history,
    get_portfolio_summary,
    get_scoped_portfolio_holdings,
    resolve_portfolio_scope,
    router,
)
from app.schemas.portfolio import PortfolioHistoryOut, ScopedPortfolioHistoryOut
from app.services.lot_accounting import PortfolioScope


NOW = datetime(2026, 6, 2, tzinfo=timezone.utc)


class _Result:
    def __init__(self, *, one=None, many=None):
        self._one = one
        self._many = list(many or [])

    def scalar_one_or_none(self):
        return self._one

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


def _buy(
    holding_id,
    ticker,
    currency,
    *,
    source_group_id=None,
    label_ids=(),
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
        transaction_labels=[
            SimpleNamespace(label_id=label_id) for label_id in label_ids
        ],
    )


def _sell(
    holding_id,
    buy_transaction,
    currency,
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


def _review_sell(
    holding_id,
    *,
    source_group_id=None,
    quantity="1",
    price="120",
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        holding_id=holding_id,
        type=TransactionType.SELL,
        quantity=Decimal(quantity),
        price=Decimal(price),
        transaction_date=date(2026, 2, 1),
        created_at=NOW,
        source_group_id=source_group_id,
        principal_flow=PrincipalFlow.REINVEST,
        requires_review=True,
        buy_lot=None,
        sell_allocations=[],
        transaction_labels=[],
    )


def _holding(
    ticker,
    currency,
    *transactions,
    name=None,
    active=True,
    snapshots=(),
):
    return SimpleNamespace(
        id=transactions[0].holding_id,
        ticker=ticker,
        name=name or ticker,
        currency=currency,
        is_active=active,
        transactions=list(transactions),
        snapshots=list(snapshots),
    )


def _snapshot(snapshot_date, close_price):
    return SimpleNamespace(
        snapshot_date=snapshot_date,
        close_price=Decimal(close_price),
    )


def test_source_scope_aggregates_same_ticker_lots_from_selected_source():
    source_a = uuid.uuid4()
    source_b = uuid.uuid4()
    holding_id = uuid.uuid4()
    holding = _holding(
        "005930",
        Currency.KRW,
        _buy(holding_id, "005930", Currency.KRW, source_group_id=source_a, quantity="1"),
        _buy(holding_id, "005930", Currency.KRW, source_group_id=source_a, quantity="2"),
        _buy(holding_id, "005930", Currency.KRW, source_group_id=source_b, quantity="4"),
    )

    summary, holdings = _build_scoped_dashboard_payload(
        [holding],
        PortfolioScope("source", source_a),
        {"005930": Decimal("120")},
    )

    assert holdings.holdings[0].remaining_quantity == Decimal("3")
    assert holdings.holdings[0].holding_id == holding_id
    assert summary.currencies[Currency.KRW].total_cost_basis == Decimal("300")


def test_unclassified_and_label_scopes_filter_lots():
    label_id = uuid.uuid4()
    holding_id = uuid.uuid4()
    holding = _holding(
        "AAPL",
        Currency.USD,
        _buy(holding_id, "AAPL", Currency.USD, quantity="2", label_ids=[label_id]),
        _buy(holding_id, "AAPL", Currency.USD, source_group_id=uuid.uuid4(), quantity="4"),
    )

    _, unclassified = _build_scoped_dashboard_payload(
        [holding],
        PortfolioScope("unclassified"),
        {"AAPL": Decimal("130")},
    )
    _, labeled = _build_scoped_dashboard_payload(
        [holding],
        PortfolioScope("label", label_id),
        {"AAPL": Decimal("130")},
    )

    assert unclassified.holdings[0].remaining_quantity == Decimal("2")
    assert labeled.holdings[0].remaining_quantity == Decimal("2")


def test_rollup_scope_counts_each_member_source_once():
    source_a = uuid.uuid4()
    source_b = uuid.uuid4()
    holding_id = uuid.uuid4()
    holding = _holding(
        "005930",
        Currency.KRW,
        _buy(holding_id, "005930", Currency.KRW, source_group_id=source_a, quantity="1"),
        _buy(holding_id, "005930", Currency.KRW, source_group_id=source_b, quantity="2"),
    )

    summary, holdings = _build_scoped_dashboard_payload(
        [holding],
        PortfolioScope(
            "rollup",
            uuid.uuid4(),
            resolved_source_group_ids=frozenset({source_a, source_a, source_b}),
        ),
        {"005930": Decimal("120")},
    )

    assert holdings.holdings[0].remaining_quantity == Decimal("3")
    assert summary.currencies[Currency.KRW].total_current_value == Decimal("360")


def test_dashboard_tracks_invested_principal_separately_from_remaining_cost_basis():
    source_id = uuid.uuid4()
    holding_id = uuid.uuid4()
    deposit_buy = _buy(
        holding_id,
        "005930",
        Currency.KRW,
        source_group_id=source_id,
        quantity="10",
        price="100",
        principal_flow=PrincipalFlow.DEPOSIT,
    )
    reinvest_buy = _buy(
        holding_id,
        "005930",
        Currency.KRW,
        source_group_id=source_id,
        quantity="5",
        price="80",
        tx_date=date(2026, 1, 2),
        principal_flow=PrincipalFlow.REINVEST,
    )
    withdrawal_sell = _sell(
        holding_id,
        deposit_buy,
        Currency.KRW,
        source_group_id=source_id,
        quantity="2",
        price="120",
        principal_flow=PrincipalFlow.WITHDRAW,
    )
    holding = _holding("005930", Currency.KRW, deposit_buy, reinvest_buy, withdrawal_sell)

    summary, holdings = _build_scoped_dashboard_payload(
        [holding],
        PortfolioScope("source", source_id),
        {"005930": Decimal("110")},
    )

    currency_summary = summary.currencies[Currency.KRW]
    assert holdings.holdings[0].remaining_cost_basis == Decimal("1200")
    assert currency_summary.total_cost_basis == Decimal("1200")
    assert currency_summary.total_invested_principal == Decimal("760")
    assert currency_summary.total_current_value == Decimal("1430")
    assert currency_summary.total_profit_loss == Decimal("670")
    assert currency_summary.total_profit_loss_pct == Decimal("88.15789473684210526315789474")


def test_dashboard_ignores_inactive_holdings_and_keeps_currencies_separate():
    krw_holding_id = uuid.uuid4()
    usd_holding_id = uuid.uuid4()
    inactive_holding_id = uuid.uuid4()
    holdings = [
        _holding("005930", Currency.KRW, _buy(krw_holding_id, "005930", Currency.KRW, quantity="2")),
        _holding("AAPL", Currency.USD, _buy(usd_holding_id, "AAPL", Currency.USD, quantity="3")),
        _holding(
            "MSFT",
            Currency.USD,
            _buy(inactive_holding_id, "MSFT", Currency.USD, quantity="99"),
            active=False,
        ),
    ]

    summary, output = _build_scoped_dashboard_payload(
        holdings,
        PortfolioScope("all"),
        {"005930": Decimal("120"), "AAPL": Decimal("130"), "MSFT": Decimal("999")},
    )

    assert [holding.ticker for holding in output.holdings] == ["005930", "AAPL"]
    assert summary.currencies[Currency.KRW].total_current_value == Decimal("240")
    assert summary.currencies[Currency.USD].total_current_value == Decimal("390")


def test_dashboard_exposes_failed_current_price_as_null():
    holding_id = uuid.uuid4()
    holding = _holding(
        "AAPL",
        Currency.USD,
        _buy(holding_id, "AAPL", Currency.USD, quantity="2"),
    )

    summary, output = _build_scoped_dashboard_payload(
        [holding],
        PortfolioScope("all"),
        {"AAPL": None},
    )

    assert output.holdings[0].current_price is None
    assert output.holdings[0].current_value is None
    assert summary.currencies[Currency.USD].total_current_value is None
    assert summary.currencies[Currency.USD].total_profit_loss is None
    assert "Current price unavailable for AAPL" in summary.warnings


def test_legacy_review_sell_returns_conservative_unavailable_dashboard():
    holding_id = uuid.uuid4()
    holding = _holding(
        "AAPL",
        Currency.USD,
        _buy(holding_id, "AAPL", Currency.USD, quantity="2"),
        _review_sell(holding_id),
    )

    summary, output = _build_scoped_dashboard_payload(
        [holding],
        PortfolioScope("all"),
        {"AAPL": Decimal("130")},
    )

    assert summary.accounting_status == "requires_review"
    assert summary.currencies[Currency.USD].total_cost_basis is None
    assert summary.currencies[Currency.USD].total_current_value is None
    assert output.accounting_status == "requires_review"
    assert output.holdings == []
    assert str(holding.transactions[1].id) in summary.warnings[0]


def test_review_sell_only_hides_affected_currency_dashboard_values():
    krw_holding_id = uuid.uuid4()
    usd_holding_id = uuid.uuid4()
    holdings = [
        _holding(
            "005930",
            Currency.KRW,
            _buy(krw_holding_id, "005930", Currency.KRW, quantity="2"),
        ),
        _holding(
            "AAPL",
            Currency.USD,
            _buy(usd_holding_id, "AAPL", Currency.USD, quantity="2"),
            _review_sell(usd_holding_id),
        ),
    ]

    summary, output = _build_scoped_dashboard_payload(
        holdings,
        PortfolioScope("all"),
        {"005930": Decimal("120"), "AAPL": Decimal("130")},
    )

    assert summary.accounting_status == "requires_review"
    assert summary.currencies[Currency.KRW].total_current_value == Decimal("240")
    assert summary.currencies[Currency.USD].total_current_value is None
    assert output.accounting_status == "requires_review"
    assert [holding.ticker for holding in output.holdings] == ["005930"]


def test_history_keeps_currencies_separate_and_carries_prior_close():
    krw_holding_id = uuid.uuid4()
    usd_holding_id = uuid.uuid4()
    holdings = [
        _holding(
            "005930",
            Currency.KRW,
            _buy(krw_holding_id, "005930", Currency.KRW, quantity="2"),
            snapshots=[_snapshot(date(2026, 1, 2), "120")],
        ),
        _holding(
            "AAPL",
            Currency.USD,
            _buy(usd_holding_id, "AAPL", Currency.USD, quantity="3", price="10"),
            snapshots=[_snapshot(date(2026, 1, 3), "12")],
        ),
    ]

    history = _build_scoped_history(holdings, PortfolioScope("all"))

    assert history.series[Currency.KRW][1].total_value == Decimal("240")
    assert history.series[Currency.USD][0].total_value is None
    assert history.series[Currency.USD][1].total_value == Decimal("36")


def test_review_history_nulls_values_that_depend_on_ambiguous_sell():
    holding_id = uuid.uuid4()
    holding = _holding(
        "AAPL",
        Currency.USD,
        _buy(holding_id, "AAPL", Currency.USD, quantity="2"),
        _review_sell(holding_id),
        snapshots=[_snapshot(date(2026, 2, 2), "130")],
    )

    point = _build_scoped_history([holding], PortfolioScope("all")).series[Currency.USD][0]

    assert point.accounting_status == "requires_review"
    assert point.total_value is None
    assert point.total_cost_basis is None
    assert point.total_profit_loss is None
    assert point.unavailable_price_count == 1


def test_history_keeps_inactive_holding_past_values():
    holding_id = uuid.uuid4()
    holding = _holding(
        "AAPL",
        Currency.USD,
        _buy(holding_id, "AAPL", Currency.USD, quantity="2"),
        active=False,
        snapshots=[_snapshot(date(2026, 1, 2), "120")],
    )

    point = _build_scoped_history([holding], PortfolioScope("all")).series[Currency.USD][0]

    assert point.total_value == Decimal("240")
    assert point.total_cost_basis == Decimal("200")


def test_review_sell_only_hides_affected_currency_history_values():
    krw_holding_id = uuid.uuid4()
    usd_holding_id = uuid.uuid4()
    holdings = [
        _holding(
            "005930",
            Currency.KRW,
            _buy(krw_holding_id, "005930", Currency.KRW, quantity="2"),
            snapshots=[_snapshot(date(2026, 2, 2), "120")],
        ),
        _holding(
            "AAPL",
            Currency.USD,
            _buy(usd_holding_id, "AAPL", Currency.USD, quantity="2"),
            _review_sell(usd_holding_id),
            snapshots=[_snapshot(date(2026, 2, 2), "130")],
        ),
    ]

    history = _build_scoped_history(holdings, PortfolioScope("all"))

    assert history.series[Currency.KRW][0].accounting_status == "ok"
    assert history.series[Currency.KRW][0].total_value == Decimal("240")
    assert history.series[Currency.USD][0].accounting_status == "requires_review"
    assert history.series[Currency.USD][0].total_value is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "scope_id", "detail"),
    [
        ("all", uuid.uuid4(), "all scope does not accept scope_id"),
        ("unclassified", uuid.uuid4(), "unclassified scope does not accept scope_id"),
        ("source", None, "source scope requires scope_id"),
        ("rollup", None, "rollup scope requires scope_id"),
        ("label", None, "label scope requires scope_id"),
    ],
)
async def test_scope_validation_rejects_invalid_scope_id_contract(kind, scope_id, detail):
    with pytest.raises(HTTPException) as exc_info:
        await resolve_portfolio_scope(_QueuedSession(), uuid.uuid4(), kind, scope_id)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "detail"),
    [
        ("source", "Source group not found"),
        ("rollup", "Rollup group not found"),
        ("label", "Label not found"),
    ],
)
async def test_cross_owner_scope_entity_is_hidden_as_not_found(kind, detail):
    db = _QueuedSession()
    db.queue(_Result(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await resolve_portfolio_scope(db, uuid.uuid4(), kind, uuid.uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == detail


@pytest.mark.asyncio
async def test_rollup_scope_resolves_current_member_rows_once():
    user_id = uuid.uuid4()
    source_a = uuid.uuid4()
    source_b = uuid.uuid4()
    rollup = RollupGroup(
        id=uuid.uuid4(),
        user_id=user_id,
        name="family",
        color="#6366f1",
        share_requires_auth=True,
        created_at=NOW,
    )
    db = _QueuedSession()
    db.queue(_Result(one=rollup), _Result(many=[source_a, source_b, source_a]))

    scope = await resolve_portfolio_scope(db, user_id, "rollup", rollup.id)

    assert scope == PortfolioScope(
        "rollup",
        rollup.id,
        resolved_source_group_ids=frozenset({source_a, source_b}),
    )
    assert db.results == []


def test_scoped_holdings_query_loads_only_owned_active_holdings():
    where_clause = str(_scoped_holdings_query(uuid.uuid4()).whereclause)

    assert "holdings.user_id" in where_clause
    assert "holdings.is_active" in where_clause


def test_scoped_history_holdings_query_can_include_inactive_holdings():
    where_clause = str(
        _scoped_holdings_query(uuid.uuid4(), include_inactive=True).whereclause
    )

    assert "holdings.user_id" in where_clause
    assert "holdings.is_active" not in where_clause


@pytest.mark.asyncio
async def test_scoped_history_loader_includes_inactive_holdings(monkeypatch):
    calls = []

    async def _load_scoped_holdings(_db, _user_id, *, include_inactive=False):
        calls.append(include_inactive)
        return []

    monkeypatch.setattr(portfolio_router, "_load_scoped_holdings", _load_scoped_holdings)

    await build_scoped_portfolio_history(_QueuedSession(), uuid.uuid4(), PortfolioScope("all"))

    assert calls == [True]


@pytest.mark.asyncio
async def test_dashboard_fetches_prices_only_for_selected_remaining_positions(monkeypatch):
    selected_source = uuid.uuid4()
    unselected_source = uuid.uuid4()
    selected_holding_id = uuid.uuid4()
    unselected_holding_id = uuid.uuid4()
    holdings = [
        _holding(
            "005930",
            Currency.KRW,
            _buy(
                selected_holding_id,
                "005930",
                Currency.KRW,
                source_group_id=selected_source,
            ),
        ),
        _holding(
            "AAPL",
            Currency.USD,
            _buy(
                unselected_holding_id,
                "AAPL",
                Currency.USD,
                source_group_id=unselected_source,
            ),
        ),
    ]
    requested_tickers = []

    async def _load_scoped_holdings(_db, _user_id, *, include_inactive=False):
        assert include_inactive is False
        return holdings

    async def _fetch_current_prices(tickers):
        requested_tickers.append(tickers)
        return {"005930": Decimal("120")}

    monkeypatch.setattr(portfolio_router, "_load_scoped_holdings", _load_scoped_holdings)
    monkeypatch.setattr(portfolio_router, "_fetch_current_prices", _fetch_current_prices)

    await build_scoped_portfolio_dashboard(
        _QueuedSession(),
        uuid.uuid4(),
        PortfolioScope("source", selected_source),
    )

    assert requested_tickers == [{"005930"}]


@pytest.mark.asyncio
async def test_summary_and_holdings_default_to_all_scope():
    user = SimpleNamespace(id=uuid.uuid4())
    summary_db = _QueuedSession()
    summary_db.queue(_Result(many=[]))
    holdings_db = _QueuedSession()
    holdings_db.queue(_Result(many=[]))

    summary = await get_portfolio_summary(current_user=user, db=summary_db)
    holdings = await get_scoped_portfolio_holdings(current_user=user, db=holdings_db)

    assert summary.accounting_status == "ok"
    assert summary.holding_count == 0
    assert holdings.accounting_status == "ok"
    assert holdings.holdings == []


@pytest.mark.asyncio
async def test_history_rejects_tag_id_with_new_scope():
    with pytest.raises(HTTPException) as exc_info:
        await get_portfolio_history(
            tag_id=uuid.uuid4(),
            scope_kind="all",
            current_user=SimpleNamespace(id=uuid.uuid4()),
            db=_QueuedSession(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "tag_id cannot be combined with scope_kind"


@pytest.mark.asyncio
async def test_history_rejects_scope_id_without_scope_kind():
    with pytest.raises(HTTPException) as exc_info:
        await get_portfolio_history(
            scope_id=uuid.uuid4(),
            current_user=SimpleNamespace(id=uuid.uuid4()),
            db=_QueuedSession(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "scope_id requires scope_kind"


def test_history_openapi_200_contract_includes_legacy_and_scoped_payloads():
    app = FastAPI()
    app.include_router(router)
    history_route = next(
        route for route in app.routes if route.path == "/api/portfolio/history"
    )

    response_schema = app.openapi()["paths"]["/api/portfolio/history"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]

    assert history_route.response_model == PortfolioHistoryOut | ScopedPortfolioHistoryOut
    assert response_schema == {
        "anyOf": [
            {"$ref": "#/components/schemas/PortfolioHistoryOut"},
            {"$ref": "#/components/schemas/ScopedPortfolioHistoryOut"},
        ],
        "title": "Response Get Portfolio History Api Portfolio History Get",
    }
