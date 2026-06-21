"""Tests for the authenticated label-scoped dashboard endpoint.

GET /api/portfolio/labels/{label_id}/dashboard
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.models.group import Label
from app.routers.deps import get_current_user, get_current_user_optional
from app.routers.groups import router as groups_router
from app.routers.portfolio import router as portfolio_router
from app.schemas.dashboard import DashboardResponse


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
        self.flush_results = []
        self.added = []
        self.deleted = []
        self.rollback_calls = 0

    def queue(self, *results):
        self.results.extend(results)

    def queue_flush(self, *results):
        self.flush_results.extend(results)

    async def execute(self, _query):
        assert self.results, "unexpected database query"
        return self.results.pop(0)

    def add(self, entity):
        if hasattr(entity, "id") and entity.id is None:
            entity.id = uuid.uuid4()
        if hasattr(entity, "created_at") and entity.created_at is None:
            entity.created_at = NOW
        self.added.append(entity)

    async def flush(self):
        if self.flush_results:
            result = self.flush_results.pop(0)
            if isinstance(result, BaseException):
                raise result
        return None

    async def rollback(self):
        self.rollback_calls += 1

    async def refresh(self, _entity, _attributes=None):
        return None

    async def delete(self, entity):
        self.deleted.append(entity)


@pytest.fixture
def user():
    return SimpleNamespace(id=uuid.uuid4())


@pytest.fixture
def db():
    return _QueuedSession()


@pytest.fixture
def client(user, db):
    app = FastAPI()
    app.include_router(groups_router)
    app.include_router(portfolio_router)

    async def _db():
        yield db

    async def _user():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_current_user_optional] = _user
    return TestClient(app)


def _label(user_id, *, name="배당주", label_id=None):
    label = Label(
        id=label_id or uuid.uuid4(),
        user_id=user_id,
        name=name,
        color="#f59e0b",
        description=None,
        share_requires_auth=True,
        created_at=NOW,
    )
    label.share_description = None
    return label


def _empty_dashboard() -> DashboardResponse:
    return DashboardResponse.model_validate({
        "display_currency": "KRW",
        "exchange_rate": None,
        "last_refreshed_at": NOW.isoformat(),
        "current_price_as_of": None,
        "comparison_as_of": None,
        "summary": {
            "total_invested_principal": None,
            "total_cost_basis": None,
            "total_current_value": None,
            "total_current_value_change": None,
            "total_unrealized_profit_loss": None,
            "total_unrealized_profit_loss_pct": None,
            "total_profit_loss": None,
            "total_profit_loss_pct": None,
        },
        "groups": [],
        "history": {"rows": []},
        "holdings": [],
        "warnings": [],
    })


def test_label_dashboard_returns_404_for_nonexistent_label(client, db):
    # Queue an empty result so resolve_portfolio_scope finds no label
    db.queue(_Result(one=None))
    response = client.get(f"/api/portfolio/labels/{uuid.uuid4()}/dashboard")
    assert response.status_code == 404


def test_label_dashboard_returns_200_for_owned_label(client, user, db, monkeypatch):
    # Step 1: create a label via the groups API
    response = client.post("/api/groups/labels", json={"name": "배당주", "color": "#f59e0b"})
    assert response.status_code == 201
    label = db.added[-1]
    label_id = label.id

    # Step 2: queue the DB lookup that resolve_portfolio_scope will make
    db.queue(_Result(one=label))

    # Step 3: stub out build_shared_portfolio_dashboard to avoid real DB/network calls
    dashboard = _empty_dashboard()
    calls = []

    async def _stub(actual_db, actual_user_id, actual_scope, display_currency="KRW"):
        calls.append((actual_user_id, actual_scope, display_currency))
        return dashboard

    monkeypatch.setattr(
        "app.routers.portfolio.build_shared_portfolio_dashboard",
        _stub,
    )

    response = client.get(
        f"/api/portfolio/labels/{label_id}/dashboard",
        params={"display_currency": "KRW"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "history" in payload
    assert "holdings" in payload
    assert payload["groups"] == []
