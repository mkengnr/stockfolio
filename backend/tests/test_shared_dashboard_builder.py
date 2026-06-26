"""Characterization tests for the real shared dashboard builder.

These call build_shared_portfolio_dashboard without stubbing it, so the
rollup child-group scoping, badge filtering, and public serialization are
exercised against real fixtures (only data loading and quotes are patched).
"""

import json
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.group import RollupGroup, RollupGroupMember, SourceGroup
from app.models.holding import Currency, Market, PrincipalFlow, TransactionType
from app.routers import portfolio as portfolio_router
from app.routers.groups import _public_shared_dashboard
from app.routers.portfolio import build_shared_portfolio_dashboard
from app.services.lot_accounting import PortfolioScope


NOW = datetime(2026, 6, 2, tzinfo=timezone.utc)
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def _source(user_id, *, name, color="#6366f1"):
    return SourceGroup(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        color=color,
        description=None,
        share_requires_auth=False,
        created_at=NOW,
    )


def _rollup(user_id, *sources, name="가족"):
    return RollupGroup(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        color="#22c55e",
        description=None,
        share_requires_auth=False,
        created_at=NOW,
        members=[RollupGroupMember(source_group_id=source.id) for source in sources],
    )


def _buy(holding_id, *, source_group_id=None, quantity="1", price="1000", label_ids=()):
    return SimpleNamespace(
        id=uuid.uuid4(),
        holding_id=holding_id,
        type=TransactionType.BUY,
        quantity=Decimal(quantity),
        price=Decimal(price),
        transaction_date=date(2026, 1, 1),
        created_at=NOW,
        source_group_id=source_group_id,
        principal_flow=PrincipalFlow.DEPOSIT,
        requires_review=False,
        buy_lot=SimpleNamespace(id=uuid.uuid4()),
        sell_allocations=[],
        transaction_labels=[
            SimpleNamespace(label_id=label_id) for label_id in label_ids
        ],
    )


def _holding(ticker, *transactions, snapshots=()):
    return SimpleNamespace(
        id=transactions[0].holding_id,
        ticker=ticker,
        market=Market.KRX,
        name=ticker,
        currency=Currency.KRW,
        is_active=True,
        transactions=list(transactions),
        snapshots=list(snapshots),
    )


def _snapshot(snapshot_date, close_price):
    return SimpleNamespace(snapshot_date=snapshot_date, close_price=Decimal(close_price))


@pytest.fixture
def shared_fixture(monkeypatch):
    user_id = uuid.uuid4()
    savings = _source(user_id, name="모음통장")
    emergency = _source(user_id, name="긴급통장", color="#dc2626")
    other = _source(user_id, name="자유통장", color="#0ea5e9")
    rollup = _rollup(user_id, savings, emergency)
    label_id = uuid.uuid4()
    holding_id = uuid.uuid4()
    holding = _holding(
        "005930",
        _buy(holding_id, source_group_id=savings.id, quantity="1", label_ids=[label_id]),
        _buy(holding_id, source_group_id=emergency.id, quantity="2"),
        _buy(holding_id, source_group_id=other.id, quantity="1"),
        snapshots=[_snapshot(date(2026, 6, 1), "1100")],
    )

    async def _load_holdings(_db, _user_id, *, include_inactive=False):
        return [holding]

    async def _load_groups(_db, _user_id):
        return [savings, emergency, other], [rollup]

    async def _quotes(tickers):
        return {
            ticker: SimpleNamespace(price=Decimal("1200"), price_date=date(2026, 6, 2))
            for ticker in tickers
        }

    monkeypatch.setattr(portfolio_router, "_load_scoped_holdings", _load_holdings)
    monkeypatch.setattr(portfolio_router, "_load_dashboard_groups", _load_groups)
    monkeypatch.setattr(portfolio_router, "_fetch_current_price_quotes", _quotes)
    return SimpleNamespace(
        user_id=user_id,
        savings=savings,
        emergency=emergency,
        other=other,
        rollup=rollup,
        label_id=label_id,
    )


def _rollup_scope(fixture):
    return PortfolioScope(
        "rollup",
        fixture.rollup.id,
        resolved_source_group_ids=frozenset(
            {fixture.savings.id, fixture.emergency.id}
        ),
    )


@pytest.mark.asyncio
async def test_rollup_share_includes_only_member_source_groups(shared_fixture):
    dashboard = await build_shared_portfolio_dashboard(
        SimpleNamespace(),
        shared_fixture.user_id,
        _rollup_scope(shared_fixture),
    )

    assert dashboard.display_currency == "KRW"
    assert dashboard.exchange_rate is None
    assert dashboard.summary.total_cost_basis == Decimal("3000")
    assert dashboard.summary.total_current_value == Decimal("3600")
    assert [(group.kind, group.name) for group in dashboard.groups] == [
        ("source", "모음통장"),
        ("source", "긴급통장"),
    ]
    assert dashboard.groups[0].summary.total_current_value == Decimal("1200")
    assert dashboard.groups[1].summary.total_current_value == Decimal("2400")

    assert len(dashboard.holdings) == 1
    row = dashboard.holdings[0]
    assert row.quantity == Decimal("3")
    assert sorted(badge.name for badge in row.groups) == ["긴급통장", "모음통장"]

    kinds_and_names = {(row.group_kind, row.group_name) for row in dashboard.history.rows}
    assert kinds_and_names == {
        ("total", "전체"),
        ("source", "모음통장"),
        ("source", "긴급통장"),
    }
    total_rows = [row for row in dashboard.history.rows if row.group_kind == "total"]
    assert total_rows[0].total_value == Decimal("3300")


@pytest.mark.asyncio
async def test_source_share_has_no_child_group_panels(shared_fixture):
    dashboard = await build_shared_portfolio_dashboard(
        SimpleNamespace(),
        shared_fixture.user_id,
        PortfolioScope("source", shared_fixture.savings.id),
    )

    assert dashboard.summary.total_current_value == Decimal("1200")
    assert dashboard.groups == []
    assert {row.group_kind for row in dashboard.history.rows} == {"total"}
    assert dashboard.holdings[0].quantity == Decimal("1")
    assert [badge.name for badge in dashboard.holdings[0].groups] == ["모음통장"]


@pytest.mark.asyncio
async def test_label_share_does_not_attach_source_group_badges(shared_fixture):
    dashboard = await build_shared_portfolio_dashboard(
        SimpleNamespace(),
        shared_fixture.user_id,
        PortfolioScope("label", shared_fixture.label_id),
    )

    assert dashboard.summary.total_current_value == Decimal("1200")
    assert dashboard.holdings[0].quantity == Decimal("1")
    assert dashboard.holdings[0].groups == []


@pytest.mark.asyncio
async def test_public_rollup_payload_contains_no_internal_uuids(shared_fixture):
    dashboard = await build_shared_portfolio_dashboard(
        SimpleNamespace(),
        shared_fixture.user_id,
        _rollup_scope(shared_fixture),
    )

    public = _public_shared_dashboard(dashboard)
    # Strip intentionally-exposed holding_ids before checking for leaked internals.
    data = public.model_dump(mode="json")
    for h in data.get("holdings", []):
        h.pop("holding_id", None)
    for g in data.get("groups", []):
        for h in g.get("holdings", []):
            h.pop("holding_id", None)
    serialized = json.dumps(data, ensure_ascii=False)
    assert not UUID_PATTERN.search(serialized)
    assert [group.key for group in public.groups] == ["group-1", "group-2"]
    assert {row.group_key for row in public.history.rows} == {
        "total",
        "group-1",
        "group-2",
    }
    badge_names = {
        badge.name for holding in public.holdings for badge in holding.groups
    }
    assert badge_names == {"모음통장", "긴급통장"}


@pytest.mark.asyncio
async def test_public_holding_exposes_holding_id(shared_fixture):
    dashboard = await build_shared_portfolio_dashboard(
        SimpleNamespace(),
        shared_fixture.user_id,
        _rollup_scope(shared_fixture),
    )

    shared = _public_shared_dashboard(dashboard)
    assert shared.holdings  # non-empty
    assert all(h.holding_id is not None for h in shared.holdings)
    for group in shared.groups:
        assert all(h.holding_id is not None for h in group.holdings)
