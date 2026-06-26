import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.group import Label, RollupGroup, RollupGroupMember, SourceGroup
from app.routers.deps import get_current_user, get_current_user_optional
from app.routers.groups import router
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
    app.include_router(router)

    async def _db():
        yield db

    async def _user():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_current_user_optional] = _user
    return TestClient(app)


def _source(user_id, *, name="월급", source_id=None):
    source = SourceGroup(
        id=source_id or uuid.uuid4(),
        user_id=user_id,
        name=name,
        color="#6366f1",
        description=None,
        share_requires_auth=True,
        share_show_transactions=False,
        created_at=NOW,
    )
    source.share_description = None
    return source


def _label(user_id, *, name="장기", label_id=None):
    label = Label(
        id=label_id or uuid.uuid4(),
        user_id=user_id,
        name=name,
        color="#6366f1",
        description=None,
        share_requires_auth=True,
        share_show_transactions=False,
        created_at=NOW,
    )
    label.share_description = None
    return label


def _rollup(user_id, *sources, name="가족", rollup_id=None):
    rollup = RollupGroup(
        id=rollup_id or uuid.uuid4(),
        user_id=user_id,
        name=name,
        color="#6366f1",
        description=None,
        share_requires_auth=True,
        share_show_transactions=False,
        created_at=NOW,
        members=[RollupGroupMember(source_group_id=source.id) for source in sources],
    )
    rollup.share_description = None
    return rollup


def test_source_group_crud_trims_name_and_normalizes_color(client, db):
    response = client.post(
        "/api/groups/sources",
        json={
            "name": "  월급  ",
            "color": "#AABBCC",
            "description": "급여",
            "share_description": "공유 화면 전용 문구",
        },
    )
    assert response.status_code == 201
    assert response.json()["name"] == "월급"
    assert response.json()["color"] == "#aabbcc"
    assert response.json()["share_description"] == "공유 화면 전용 문구"
    source = db.added[-1]

    db.queue(_Result(many=[source]))
    response = client.get("/api/groups/sources")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(source.id)]

    db.queue(_Result(one=source))
    response = client.get(f"/api/groups/sources/{source.id}")
    assert response.status_code == 200
    assert response.json()["name"] == "월급"

    db.queue(_Result(one=source))
    response = client.put(
        f"/api/groups/sources/{source.id}",
        json={"name": "  비상금  ", "share_description": "비상금 공유 안내"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "비상금"
    assert response.json()["share_description"] == "비상금 공유 안내"

    db.queue(_Result(one=source), _Result(), _Result(), _Result())
    response = client.delete(f"/api/groups/sources/{source.id}")
    assert response.status_code == 204
    assert db.deleted == [source]


def test_label_crud(client, user, db):
    response = client.post("/api/groups/labels", json={"name": "  장기  "})
    assert response.status_code == 201
    label = db.added[-1]
    assert response.json()["name"] == "장기"

    db.queue(_Result(many=[label]))
    assert client.get("/api/groups/labels").json()[0]["id"] == str(label.id)

    db.queue(_Result(one=label))
    response = client.get(f"/api/groups/labels/{label.id}")
    assert response.status_code == 200

    db.queue(_Result(one=label))
    response = client.put(f"/api/groups/labels/{label.id}", json={"name": "  단기  "})
    assert response.status_code == 200
    assert response.json()["name"] == "단기"

    db.queue(_Result(one=label), _Result())
    response = client.delete(f"/api/groups/labels/{label.id}")
    assert response.status_code == 204
    assert db.deleted == [label]


def test_rollup_group_crud_accepts_only_owned_source_members(client, user, db):
    source_a = _source(user.id, name="월급")
    source_b = _source(user.id, name="비상금")
    db.queue(_Result(many=[source_a.id, source_b.id]))

    response = client.post(
        "/api/groups/rollups",
        json={
            "name": "  가족  ",
            "source_group_ids": [str(source_a.id), str(source_b.id)],
        },
    )
    assert response.status_code == 201
    rollup = next(entity for entity in db.added if isinstance(entity, RollupGroup))
    assert response.json()["name"] == "가족"
    assert response.json()["source_group_ids"] == sorted([str(source_a.id), str(source_b.id)])
    created_members = [
        entity
        for entity in db.added
        if isinstance(entity, RollupGroupMember)
    ]
    assert {entity.source_group_id for entity in created_members} == {source_a.id, source_b.id}
    rollup.members = created_members

    db.queue(_Result(many=[rollup]))
    assert client.get("/api/groups/rollups").json()[0]["id"] == str(rollup.id)

    db.queue(_Result(one=rollup))
    assert client.get(f"/api/groups/rollups/{rollup.id}").status_code == 200

    db.queue(_Result(one=rollup), _Result(many=[source_b.id]))
    response = client.put(
        f"/api/groups/rollups/{rollup.id}",
        json={"source_group_ids": [str(source_b.id)]},
    )
    assert response.status_code == 200
    assert response.json()["source_group_ids"] == [str(source_b.id)]
    assert source_a.id in {
        member.source_group_id
        for member in db.deleted
        if isinstance(member, RollupGroupMember)
    }

    rollup.members = []
    db.deleted.clear()
    db.queue(_Result(one=rollup), _Result())
    response = client.delete(f"/api/groups/rollups/{rollup.id}")
    assert response.status_code == 204
    assert db.deleted == [rollup]


def test_rollup_group_rejects_duplicate_members(client, user, db):
    source = _source(user.id)
    response = client.post(
        "/api/groups/rollups",
        json={"name": "가족", "source_group_ids": [str(source.id), str(source.id)]},
    )
    assert response.status_code == 422
    assert db.results == []


def test_rollup_group_rejects_nested_rollup_shape(client):
    response = client.post(
        "/api/groups/rollups",
        json={"name": "가족", "rollup_group_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 422


def test_rollup_group_hides_cross_user_source_member(client, user, db):
    owned = _source(user.id)
    other_id = uuid.uuid4()
    db.queue(_Result(many=[owned.id]))
    response = client.post(
        "/api/groups/rollups",
        json={"name": "가족", "source_group_ids": [str(owned.id), str(other_id)]},
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "kind", "suffix", "body"),
    [
        ("put", "sources", "", {"name": "침범"}),
        ("put", "rollups", "", {"name": "침범"}),
        ("put", "labels", "", {"name": "침범"}),
        ("delete", "sources", "", None),
        ("delete", "rollups", "", None),
        ("delete", "labels", "", None),
        ("post", "sources", "/share", {"requires_auth": False}),
        ("post", "rollups", "/share", {"requires_auth": False}),
        ("post", "labels", "/share", {"requires_auth": False}),
        ("delete", "sources", "/share", None),
        ("delete", "rollups", "/share", None),
        ("delete", "labels", "/share", None),
    ],
)
def test_cross_user_mutations_hide_groups(client, db, method, kind, suffix, body):
    # The fake does not evaluate SQL predicates; an empty owned lookup verifies the route contract.
    db.queue(_Result())
    response = client.request(
        method,
        f"/api/groups/{kind}/{uuid.uuid4()}{suffix}",
        json=body,
    )
    assert response.status_code == 404
    assert db.deleted == []


@pytest.mark.parametrize(
    ("kind", "entity", "reference_results"),
    [
        ("sources", _source(uuid.uuid4()), [_Result(one=object())]),
        ("sources", _source(uuid.uuid4()), [_Result(), _Result(one=object())]),
        ("sources", _source(uuid.uuid4()), [_Result(), _Result(), _Result(one=object())]),
        ("labels", _label(uuid.uuid4()), [_Result(one=object())]),
        ("rollups", _rollup(uuid.uuid4(), _source(uuid.uuid4())), [_Result(one=object())]),
    ],
)
def test_delete_referenced_entity_returns_conflict(client, db, kind, entity, reference_results):
    db.queue(_Result(one=entity), *reference_results)
    response = client.delete(f"/api/groups/{kind}/{entity.id}")
    assert response.status_code == 409
    assert db.deleted == []


def test_delete_restrict_race_returns_conflict_after_rollback(client, user, db):
    source = _source(user.id)
    db.queue(_Result(one=source), _Result(), _Result(), _Result())
    db.queue_flush(IntegrityError("delete source group", {}, Exception("restrict race")))

    response = client.delete(f"/api/groups/sources/{source.id}")

    assert response.status_code == 409
    assert response.json() == {"detail": "Referenced group cannot be deleted"}
    assert db.deleted == [source]
    assert db.rollback_calls == 1


def test_create_rollup_member_race_returns_conflict_after_rollback(client, user, db):
    source = _source(user.id)
    db.queue(_Result(many=[source.id]))
    db.queue_flush(None, IntegrityError("insert rollup member", {}, Exception("foreign key race")))

    response = client.post(
        "/api/groups/rollups",
        json={"name": "가족", "source_group_ids": [str(source.id)]},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Rollup group membership conflict"}
    assert db.rollback_calls == 1


def test_update_rollup_mixed_member_race_returns_conflict_after_rollback(client, user, db):
    source_a = _source(user.id, name="월급")
    source_b = _source(user.id, name="비상금")
    source_c = _source(user.id, name="연금")
    rollup = _rollup(user.id, source_a, source_b)
    db.queue(_Result(one=rollup), _Result(many=[source_b.id, source_c.id]))
    db.queue_flush(IntegrityError("update rollup members", {}, Exception("foreign key race")))

    response = client.put(
        f"/api/groups/rollups/{rollup.id}",
        json={"source_group_ids": [str(source_b.id), str(source_c.id)]},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Rollup group membership conflict"}
    assert any(
        isinstance(entity, RollupGroupMember) and entity.source_group_id == source_a.id
        for entity in db.deleted
    )
    assert any(
        isinstance(entity, RollupGroupMember) and entity.source_group_id == source_c.id
        for entity in db.added
    )
    assert db.rollback_calls == 1


@pytest.mark.parametrize(
    ("kind", "entity_factory"),
    [("sources", _source), ("rollups", _rollup), ("labels", _label)],
)
def test_share_mutations_support_every_group_kind(client, user, db, kind, entity_factory):
    entity = entity_factory(user.id)
    db.queue(_Result(one=entity))
    response = client.post(
        f"/api/groups/{kind}/{entity.id}/share",
        json={"requires_auth": False},
    )
    assert response.status_code == 200
    uuid.UUID(response.json()["share_token"])
    assert response.json()["share_requires_auth"] is False

    db.queue(_Result(one=entity))
    response = client.delete(f"/api/groups/{kind}/{entity.id}/share")
    assert response.status_code == 204
    assert entity.share_token is None


@pytest.mark.parametrize(
    ("kind", "entity", "lookup_results"),
    [
        ("source", _source(uuid.uuid4()), []),
        ("rollup", _rollup(uuid.uuid4()), [_Result()]),
        ("label", _label(uuid.uuid4()), [_Result(), _Result()]),
    ],
)
def test_anonymous_public_share_returns_scoped_dashboard_without_internal_ids(
    client,
    db,
    monkeypatch,
    kind,
    entity,
    lookup_results,
):
    entity.share_token = str(uuid.uuid4())
    entity.share_requires_auth = False
    db.queue(*lookup_results, _Result(one=entity))
    scope = object()
    calls = []

    async def _resolve_portfolio_scope(actual_db, user_id, scope_kind, scope_id):
        calls.append(("scope", actual_db, user_id, scope_kind, scope_id))
        return scope

    dashboard = DashboardResponse.model_validate({
        "display_currency": "KRW",
        "exchange_rate": None,
        "last_refreshed_at": NOW.isoformat(),
        "current_price_as_of": "2026-06-02",
        "comparison_as_of": "2026-06-01",
        "price_dates_by_market": {"KRX": "2026-06-23", "US": "2026-06-22"},
        "comparison_dates_by_market": {"KRX": "2026-06-20", "US": "2026-06-18"},
        "daily_change_active_by_market": {"KRX": False, "US": True},
        "summary": {
            "total_invested_principal": "70000",
            "total_cost_basis": "70000",
            "total_current_value": "75000",
            "total_current_value_change": "1000",
            "total_unrealized_profit_loss": "5000",
            "total_unrealized_profit_loss_pct": "7.14",
            "total_profit_loss": "5000",
            "total_profit_loss_pct": "7.14",
        },
        "groups": [
            {
                "kind": "source",
                "id": str(entity.id),
                "name": entity.name,
                "color": entity.color,
                "source_group_ids": [str(entity.id)],
                "summary": {
                    "total_invested_principal": "70000",
                    "total_cost_basis": "70000",
                    "total_current_value": "75000",
                    "total_current_value_change": "1000",
                    "total_unrealized_profit_loss": "5000",
                    "total_unrealized_profit_loss_pct": "7.14",
                    "total_profit_loss": "5000",
                    "total_profit_loss_pct": "7.14",
                },
                "holdings": [],
            }
        ],
        "history": {
            "rows": [
                {
                    "group_kind": "source",
                    "group_id": str(entity.id),
                    "group_name": entity.name,
                    "snapshot_date": "2026-06-01",
                    "total_value": "75000",
                    "total_invested_principal": "70000",
                    "total_cost_basis": "70000",
                    "total_profit_loss": "5000",
                }
            ]
        },
        "holdings": [
            {
                "holding_id": str(uuid.uuid4()),
                "ticker": "AAPL",
                "name": "Apple",
                "market": "US",
                "currency": "USD",
                "quantity": "1",
                "remaining_cost_basis": "70000",
                "current_price": "75000",
                "current_value": "75000",
                "current_value_change": "1000",
                "unrealized_profit_loss": "5000",
                "groups": [
                    {
                        "source_group_id": str(entity.id),
                        "name": entity.name,
                        "color": entity.color,
                        "remaining_quantity": "1",
                    }
                ],
            }
        ],
        "warnings": [
            "AAPL 현재가 기준일이 시장 날짜보다 미래입니다: 2026-06-23",
            "Current price unavailable for AAPL",
            "USD/KRW exchange rate lookup failed",
        ],
    })

    async def _build_shared_portfolio_dashboard(actual_db, user_id, actual_scope):
        calls.append(("shared_dashboard", actual_db, user_id, actual_scope))
        return dashboard

    monkeypatch.setattr(
        "app.routers.groups.resolve_portfolio_scope",
        _resolve_portfolio_scope,
    )
    monkeypatch.setattr(
        "app.routers.groups.build_shared_portfolio_dashboard",
        _build_shared_portfolio_dashboard,
    )

    response = client.get(f"/api/groups/share/{entity.share_token}")
    assert response.status_code == 200
    assert response.json() == {
        "kind": kind,
        "name": entity.name,
        "color": "#6366f1",
        "description": None,
        "share_description": None,
        "dashboard": {
            "display_currency": "KRW",
            "price_dates_by_market": {"KRX": "2026-06-23", "US": "2026-06-22"},
            "comparison_dates_by_market": {"KRX": "2026-06-20", "US": "2026-06-18"},
            "daily_change_active_by_market": {"KRX": False, "US": True},
            "warnings": [
                "AAPL 현재가 기준일이 시장 날짜보다 미래입니다: 2026-06-23",
                "Current price unavailable for AAPL",
                "USD/KRW exchange rate lookup failed",
            ],
            "summary": {
                "total_invested_principal": "70000",
                "total_cost_basis": "70000",
                "total_current_value": "75000",
                "total_current_value_change": "1000",
                "total_current_value_change_pct": None,
                "total_unrealized_profit_loss": "5000",
                "total_unrealized_profit_loss_pct": "7.14",
                "total_profit_loss": "5000",
                "total_profit_loss_pct": "7.14",
            },
            "groups": [
                {
                    "key": "group-1",
                    "kind": "source",
                    "name": entity.name,
                    "color": entity.color,
                    "summary": {
                        "total_invested_principal": "70000",
                        "total_cost_basis": "70000",
                        "total_current_value": "75000",
                        "total_current_value_change": "1000",
                        "total_current_value_change_pct": None,
                        "total_unrealized_profit_loss": "5000",
                        "total_unrealized_profit_loss_pct": "7.14",
                        "total_profit_loss": "5000",
                        "total_profit_loss_pct": "7.14",
                    },
                    "holdings": [],
                }
            ],
            "history": {
                "rows": [
                    {
                        "group_key": "group-1",
                        "group_kind": "source",
                        "group_name": entity.name,
                        "snapshot_date": "2026-06-01",
                        "total_value": "75000",
                        "total_invested_principal": "70000",
                        "total_cost_basis": "70000",
                        "total_profit_loss": "5000",
                    }
                ]
            },
            "holdings": [
                {
                    "ticker": "AAPL",
                    "name": "Apple",
                    "market": "US",
                    "currency": "USD",
                    "quantity": "1",
                    "remaining_cost_basis": "70000",
                    "current_price": "75000",
                    "current_value": "75000",
                    "current_value_change": "1000",
                    "unrealized_profit_loss": "5000",
                    "groups": [
                        {
                            "name": entity.name,
                            "color": entity.color,
                            "remaining_quantity": "1",
                        }
                    ],
                }
            ],
        },
    }
    assert calls == [
        ("scope", db, entity.user_id, kind, entity.id),
        ("shared_dashboard", db, entity.user_id, scope),
    ]


def test_public_share_omits_internal_warnings_and_legacy_fields(client, user, db, monkeypatch):
    source = _source(user.id)
    source.share_token = str(uuid.uuid4())
    source.share_requires_auth = False
    db.queue(_Result(one=source))
    transaction_id = uuid.uuid4()
    internal_warning = (
        f"Sell transaction {transaction_id} requires review: lot allocations are missing"
    )
    public_warnings = [
        "US 일부 종목의 현재가 기준일이 다릅니다: 2026-06-20 ~ 2026-06-22",
        "US 장중 현재가입니다.",
        "USD/KRW exchange rate lookup failed",
    ]
    unrelated_ticker_warnings = [
        "AAPL 현재가 기준일이 시장 날짜보다 미래입니다: 2026-06-23",
        "Current price unavailable for AAPL",
        "AAPL 직전 거래일 스냅샷 복구 실패",
        "US 장중 현재가입니다. 차트는 직전 확정 종가까지 표시됩니다.",
    ]

    async def _resolve_portfolio_scope(*_args):
        return object()

    dashboard = DashboardResponse.model_validate({
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
        "warnings": [
            internal_warning,
            *unrelated_ticker_warnings,
            *public_warnings,
            public_warnings[0],
        ],
    })

    async def _build_shared_portfolio_dashboard(*_args):
        return dashboard

    monkeypatch.setattr("app.routers.groups.resolve_portfolio_scope", _resolve_portfolio_scope)
    monkeypatch.setattr(
        "app.routers.groups.build_shared_portfolio_dashboard",
        _build_shared_portfolio_dashboard,
    )

    response = client.get(f"/api/groups/share/{source.share_token}")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"kind", "name", "color", "description", "share_description", "dashboard"}
    assert payload["dashboard"]["warnings"] == public_warnings
    assert internal_warning not in response.text
    assert str(transaction_id) not in response.text
    assert "exchange_rate" not in payload["dashboard"]
    assert "last_refreshed_at" not in payload["dashboard"]



def test_public_share_honors_authentication_gate(client, user, db):
    source = _source(user.id)
    source.share_token = str(uuid.uuid4())
    db.queue(_Result(one=source))

    async def _anonymous():
        return None

    client.app.dependency_overrides[get_current_user_optional] = _anonymous
    response = client.get(f"/api/groups/share/{source.share_token}")
    assert response.status_code == 401


def test_public_share_token_must_be_uuid(client):
    response = client.get("/api/groups/share/not-a-uuid")
    assert response.status_code == 422


@pytest.mark.parametrize("body", [{"name": "   "}, {"name": "valid", "color": "blue"}])
def test_source_group_rejects_invalid_metadata(client, body):
    response = client.post("/api/groups/sources", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize("kind", ["sources", "rollups", "labels"])
def test_group_create_rejects_name_longer_than_50_trimmed_characters(client, kind):
    response = client.post(f"/api/groups/{kind}", json={"name": f"  {'x' * 51}  "})
    assert response.status_code == 422


@pytest.mark.parametrize("kind", ["sources", "rollups", "labels"])
def test_group_update_rejects_name_longer_than_50_trimmed_characters(client, kind):
    response = client.put(
        f"/api/groups/{kind}/{uuid.uuid4()}",
        json={"name": f"  {'x' * 51}  "},
    )
    assert response.status_code == 422


def test_main_app_registers_group_router():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/groups/sources" in paths
    assert "/api/groups/share/{token}" in paths


@pytest.fixture
def source(user, db):
    s = _source(user.id)
    db.queue(_Result(one=s))
    return s


def test_enable_share_persists_show_transactions(client, db, source):
    response = client.post(
        f"/api/groups/sources/{source.id}/share",
        json={"requires_auth": False, "show_transactions": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["share_token"]
    assert body["share_show_transactions"] is True
    assert source.share_show_transactions is True


def test_enable_share_defaults_show_transactions_false(client, db, source):
    response = client.post(
        f"/api/groups/sources/{source.id}/share",
        json={"requires_auth": False},
    )
    assert response.status_code == 200
    assert response.json()["share_show_transactions"] is False


def test_update_share_settings_toggles_show_transactions(client, db, source):
    # source fixture already queued one result for the POST; queue a second for the PATCH
    db.queue(_Result(one=source))

    client.post(f"/api/groups/sources/{source.id}/share", json={"requires_auth": True})
    token_before = source.share_token

    response = client.patch(
        f"/api/groups/sources/{source.id}/share",
        json={"show_transactions": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["share_show_transactions"] is True
    assert body["share_requires_auth"] is True  # unspecified field unchanged
    assert body["share_token"] == token_before    # token not regenerated


def test_update_share_settings_rejects_unshared_group(client, db, source):
    # source fixture queued one result; source has no share_token by default
    response = client.patch(
        f"/api/groups/sources/{source.id}/share",
        json={"show_transactions": True},
    )
    assert response.status_code == 409
