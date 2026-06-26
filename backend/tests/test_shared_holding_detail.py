import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.models.group import SourceGroup
from app.routers.deps import get_current_user, get_current_user_optional
from app.routers.groups import (
    _scoped_shared_transactions,
    _shared_holding_in_scope,
    router,
)
from app.models.holding import Currency, Market, PrincipalFlow, TransactionType
from app.services.lot_accounting import PortfolioScope


NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures mirroring tests/test_holding_performance_scope.py
# ---------------------------------------------------------------------------


def _tx(*, tx_id, sgid, type_, qty, price, day, lot_id=None, allocations=(), labels=()):
    return SimpleNamespace(
        id=tx_id,
        source_group_id=sgid,
        type=type_,
        quantity=Decimal(qty),
        price=Decimal(price),
        transaction_date=date(2026, 1, day),
        created_at=NOW,
        principal_flow=(
            PrincipalFlow.DEPOSIT if type_ == TransactionType.BUY else PrincipalFlow.WITHDRAW
        ),
        requires_review=False,
        buy_lot=SimpleNamespace(id=lot_id) if lot_id else None,
        sell_allocations=list(allocations),
        transaction_labels=[SimpleNamespace(label_id=lid) for lid in labels],
    )


def _holding(transactions):
    return SimpleNamespace(
        id=uuid.uuid4(),
        ticker="005930",
        currency=Currency.KRW,
        market=Market.KRX,
        name="삼성전자",
        transactions=transactions,
    )


# ---------------------------------------------------------------------------
# (a) UNIT tests for the scope helpers
# ---------------------------------------------------------------------------


def test_shared_holding_in_scope_true_when_lot_in_scope():
    sg_a = uuid.uuid4()
    lot_a = uuid.uuid4()
    holding = _holding(
        [
            _tx(
                tx_id=uuid.uuid4(),
                sgid=sg_a,
                type_=TransactionType.BUY,
                qty="10",
                price="100",
                day=1,
                lot_id=lot_a,
            )
        ]
    )
    assert _shared_holding_in_scope(holding, PortfolioScope("source", sg_a)) is True


def test_shared_holding_in_scope_false_when_no_lot_in_scope():
    sg_a, sg_other = uuid.uuid4(), uuid.uuid4()
    lot_a = uuid.uuid4()
    holding = _holding(
        [
            _tx(
                tx_id=uuid.uuid4(),
                sgid=sg_a,
                type_=TransactionType.BUY,
                qty="10",
                price="100",
                day=1,
                lot_id=lot_a,
            )
        ]
    )
    # The holding's only lot belongs to sg_a; a share scoped to sg_other must
    # not see (and so must not leak) it.
    assert _shared_holding_in_scope(holding, PortfolioScope("source", sg_other)) is False


def test_scoped_shared_transactions_returns_only_in_scope_source():
    sg_a, sg_b = uuid.uuid4(), uuid.uuid4()
    lot_a, lot_b = uuid.uuid4(), uuid.uuid4()
    holding = _holding(
        [
            _tx(
                tx_id=uuid.uuid4(),
                sgid=sg_a,
                type_=TransactionType.BUY,
                qty="10",
                price="100",
                day=1,
                lot_id=lot_a,
            ),
            _tx(
                tx_id=uuid.uuid4(),
                sgid=sg_b,
                type_=TransactionType.BUY,
                qty="5",
                price="200",
                day=2,
                lot_id=lot_b,
            ),
        ]
    )
    result = _scoped_shared_transactions(holding, PortfolioScope("source", sg_a))
    assert len(result) == 1
    assert result[0].type == "BUY"
    assert result[0].quantity == Decimal("10")
    assert result[0].price == Decimal("100")


def test_scoped_shared_transactions_empty_when_no_match():
    sg_a, sg_other = uuid.uuid4(), uuid.uuid4()
    lot_a = uuid.uuid4()
    holding = _holding(
        [
            _tx(
                tx_id=uuid.uuid4(),
                sgid=sg_a,
                type_=TransactionType.BUY,
                qty="10",
                price="100",
                day=1,
                lot_id=lot_a,
            )
        ]
    )
    assert _scoped_shared_transactions(holding, PortfolioScope("source", sg_other)) == []


def test_scoped_shared_transactions_all_scope_returns_everything():
    sg_a, sg_b = uuid.uuid4(), uuid.uuid4()
    lot_a, lot_b = uuid.uuid4(), uuid.uuid4()
    holding = _holding(
        [
            _tx(
                tx_id=uuid.uuid4(),
                sgid=sg_a,
                type_=TransactionType.BUY,
                qty="10",
                price="100",
                day=1,
                lot_id=lot_a,
            ),
            _tx(
                tx_id=uuid.uuid4(),
                sgid=sg_b,
                type_=TransactionType.BUY,
                qty="5",
                price="200",
                day=2,
                lot_id=lot_b,
            ),
        ]
    )
    assert len(_scoped_shared_transactions(holding, PortfolioScope("all"))) == 2


# ---------------------------------------------------------------------------
# (b) API-level tests for the auth / not-found gates (FakeSession pattern)
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, *, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one


class _QueuedSession:
    def __init__(self):
        self.results = []

    def queue(self, *results):
        self.results.extend(results)

    async def execute(self, _query):
        assert self.results, "unexpected database query"
        return self.results.pop(0)


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


def _source(user_id, *, requires_auth=True):
    source = SourceGroup(
        id=uuid.uuid4(),
        user_id=user_id,
        name="월급",
        color="#6366f1",
        description=None,
        share_requires_auth=requires_auth,
        share_show_transactions=False,
        created_at=NOW,
    )
    source.share_description = None
    source.share_token = str(uuid.uuid4())
    return source


def test_unknown_token_returns_404(client, db):
    # All three model lookups (source, rollup, label) miss.
    db.queue(_Result(one=None), _Result(one=None), _Result(one=None))
    response = client.get(
        f"/api/groups/share/{uuid.uuid4()}/holdings/{uuid.uuid4()}"
    )
    assert response.status_code == 404


def test_requires_auth_anonymous_returns_401(client, user, db):
    source = _source(user.id, requires_auth=True)
    # First (source) lookup hits the entity; the requires_auth gate fires before
    # any further query, so only one result needs to be queued.
    db.queue(_Result(one=source))

    async def _anonymous():
        return None

    client.app.dependency_overrides[get_current_user_optional] = _anonymous
    response = client.get(
        f"/api/groups/share/{source.share_token}/holdings/{uuid.uuid4()}"
    )
    assert response.status_code == 401


def test_share_token_must_be_uuid(client):
    response = client.get(
        f"/api/groups/share/not-a-uuid/holdings/{uuid.uuid4()}"
    )
    assert response.status_code == 422
