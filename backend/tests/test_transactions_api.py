import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.database import get_db
from app.models.group import BuyLot, Label, SellLotAllocation, SourceGroup, TransactionLabel
from app.models.holding import Currency, Holding, Market, PrincipalFlow, Transaction, TransactionType
from app.routers.deps import get_current_user
from app.routers.transactions import router


NOW = datetime(2026, 6, 2, tzinfo=timezone.utc)


class _Result:
    def __init__(self, *, one=None, many=None, count=None):
        self._one = one
        self._many = list(many or [])
        self._count = count

    def scalar_one_or_none(self):
        return self._one

    def scalar_one(self):
        return self._count

    def scalars(self):
        return self

    def all(self):
        return self._many


class _QueuedSession:
    def __init__(self):
        self.results = []
        self.added = []
        self.deleted = []
        self.queries = []

    def queue(self, *results):
        self.results.extend(results)

    async def execute(self, query):
        self.queries.append(str(query))
        assert self.results, "unexpected database query"
        return self.results.pop(0)

    def add(self, entity):
        if getattr(entity, "id", None) is None:
            entity.id = uuid.uuid4()
        if hasattr(entity, "created_at") and entity.created_at is None:
            entity.created_at = NOW
        self.added.append(entity)

    async def flush(self):
        for entity in self.added:
            if getattr(entity, "id", None) is None:
                entity.id = uuid.uuid4()
            if hasattr(entity, "created_at") and entity.created_at is None:
                entity.created_at = NOW

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
    return _client(user, db)


def _client(user, db, *, authenticated=True):
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    async def _user():
        if not authenticated:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


def _source(user_id, *, name="월급"):
    return SourceGroup(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        color="#6366f1",
        share_requires_auth=True,
        created_at=NOW,
    )


def _label(user_id, *, name="장기"):
    return Label(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        color="#6366f1",
        share_requires_auth=True,
        created_at=NOW,
    )


def _holding(user_id, *, ticker="005930", name="삼성전자"):
    return Holding(
        id=uuid.uuid4(),
        user_id=user_id,
        ticker=ticker,
        market=Market.KRX,
        name=name,
        quantity=Decimal("0"),
        avg_price=Decimal("0"),
        currency=Currency.KRW,
        first_buy_date=date(2026, 1, 1),
        is_active=True,
        transactions=[],
        buy_lots=[],
    )


def _attach_label(tx, label):
    tx.transaction_labels.append(
        TransactionLabel(transaction_id=tx.id, label_id=label.id, label=label)
    )


def _buy(
    holding,
    *,
    source=None,
    quantity="2",
    price="80000",
    principal_flow=PrincipalFlow.DEPOSIT,
    transaction_date=date(2026, 1, 1),
):
    tx = Transaction(
        id=uuid.uuid4(),
        holding_id=holding.id,
        user_id=holding.user_id,
        source_group_id=source.id if source else None,
        source_group=source,
        type=TransactionType.BUY,
        quantity=Decimal(quantity),
        price=Decimal(price),
        transaction_date=transaction_date,
        principal_flow=principal_flow,
        created_at=NOW,
        requires_review=False,
        transaction_labels=[],
        sell_allocations=[],
    )
    lot = BuyLot(
        id=uuid.uuid4(),
        transaction_id=tx.id,
        holding_id=holding.id,
        user_id=holding.user_id,
        source_group_id=tx.source_group_id,
        original_quantity=Decimal(quantity),
        remaining_quantity=Decimal(quantity),
        unit_price=Decimal(price),
    )
    tx.buy_lot = lot
    holding.transactions.append(tx)
    holding.buy_lots.append(lot)
    holding.quantity += tx.quantity
    holding.avg_price = tx.price
    return tx, lot


def _sell(
    holding,
    lot,
    *,
    source=None,
    quantity="1",
    price="100000",
    principal_flow=PrincipalFlow.REINVEST,
    transaction_date=date(2026, 2, 1),
):
    tx = Transaction(
        id=uuid.uuid4(),
        holding_id=holding.id,
        user_id=holding.user_id,
        source_group_id=source.id if source else None,
        source_group=source,
        type=TransactionType.SELL,
        quantity=Decimal(quantity),
        price=Decimal(price),
        transaction_date=transaction_date,
        principal_flow=principal_flow,
        created_at=NOW,
        requires_review=False,
        transaction_labels=[],
        sell_allocations=[],
    )
    allocation = SellLotAllocation(
        id=uuid.uuid4(),
        sell_transaction_id=tx.id,
        buy_lot_id=lot.id,
        buy_lot=lot,
        quantity=Decimal(quantity),
    )
    tx.sell_allocations.append(allocation)
    holding.transactions.append(tx)
    holding.quantity -= tx.quantity
    lot.remaining_quantity -= tx.quantity
    return tx


def test_transactions_list_requires_authentication(user, db):
    response = _client(user, db, authenticated=False).get("/api/transactions")

    assert response.status_code == 401


def test_list_paginates_with_limit_offset_and_total(client, user, db):
    holding = _holding(user.id)
    tx, _ = _buy(holding)
    db.queue(_Result(count=3), _Result(many=[tx]))

    response = client.get("/api/transactions", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert len(payload["transactions"]) == 1


def test_list_rejects_limit_above_cap(client, user, db):
    response = client.get("/api/transactions", params={"limit": 501})

    assert response.status_code == 422


def test_list_returns_owned_transactions_with_metadata_and_amount(client, user, db):
    source = _source(user.id)
    label = _label(user.id)
    holding = _holding(user.id)
    tx, _ = _buy(holding, source=source, quantity="2", price="80000")
    _attach_label(tx, label)
    db.queue(_Result(count=1), _Result(many=[tx]))

    response = client.get("/api/transactions")

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "limit": 200,
        "offset": 0,
        "transactions": [
            {
                "id": str(tx.id),
                "holding_id": str(holding.id),
                "ticker": "005930",
                "holding_name": "삼성전자",
                "currency": "KRW",
                "type": "BUY",
                "transaction_date": "2026-01-01",
                "quantity": "2",
                "price": "80000",
                "amount": "160000",
                "principal_flow": "DEPOSIT",
                "source_group_id": str(source.id),
                "source_group_name": "월급",
                "label_ids": [str(label.id)],
                "label_names": ["장기"],
                "requires_review": False,
                "created_at": "2026-06-02T00:00:00Z",
            }
        ]
    }


def test_list_builds_query_with_supported_filters(client, user, db):
    source = _source(user.id)
    holding = _holding(user.id)
    tx, _ = _buy(holding, source=source)
    db.queue(_Result(count=1), _Result(many=[tx]))

    response = client.get(
        "/api/transactions",
        params={
            "q": "삼성",
            "type": "BUY",
            "principal_flow": "DEPOSIT",
            "source_group_id": str(source.id),
            "requires_review": "false",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        },
    )

    assert response.status_code == 200
    compiled_query = db.queries[0]
    assert "transactions.type" in compiled_query
    assert "transactions.principal_flow" in compiled_query
    assert "transactions.source_group_id" in compiled_query
    assert "transactions.requires_review" in compiled_query
    assert "transactions.transaction_date" in compiled_query
    assert "holdings.ticker" in compiled_query
    assert "holdings.name" in compiled_query
    assert "holdings.user_id" in compiled_query


def test_cross_user_transaction_patch_and_delete_are_hidden(client, db):
    db.queue(_Result(one=None), _Result(one=None))
    tx_id = uuid.uuid4()

    patch_response = client.patch(
        f"/api/transactions/{tx_id}",
        json={"price": "85000"},
    )
    delete_response = client.delete(f"/api/transactions/{tx_id}")

    assert patch_response.status_code == 404
    assert delete_response.status_code == 404


def test_buy_patch_updates_lot_holding_labels_and_rebuilds_snapshots(client, user, db):
    original_source = _source(user.id, name="기존")
    new_source = _source(user.id, name="신규")
    label = _label(user.id)
    holding = _holding(user.id)
    tx, lot = _buy(holding, source=original_source, quantity="2", price="80000")
    db.queue(
        _Result(one=holding.id),
        _Result(one=holding),
        _Result(one=new_source),
        _Result(many=[label]),
        _Result(many=[new_source]),
        _Result(many=[label]),
    )

    with patch("app.routers.transactions.rebuild_holding_snapshots", new=AsyncMock()) as rebuild:
        response = client.patch(
            f"/api/transactions/{tx.id}",
            json={
                "transaction_date": "2026-01-10",
                "quantity": "3",
                "price": "90000",
                "principal_flow": "REINVEST",
                "source_group_id": str(new_source.id),
                "label_ids": [str(label.id)],
            },
        )

    assert response.status_code == 200
    assert tx.transaction_date == date(2026, 1, 10)
    assert tx.quantity == Decimal("3")
    assert tx.price == Decimal("90000")
    assert tx.principal_flow == PrincipalFlow.REINVEST
    assert tx.source_group_id == new_source.id
    assert lot.original_quantity == Decimal("3")
    assert lot.unit_price == Decimal("90000")
    assert lot.source_group_id == new_source.id
    assert lot.remaining_quantity == Decimal("3")
    assert holding.quantity == Decimal("3")
    assert holding.avg_price == Decimal("90000")
    assert response.json()["label_ids"] == [str(label.id)]
    assert response.json()["source_group_name"] == "신규"
    assert response.json()["label_names"] == ["장기"]
    rebuild.assert_awaited_once_with(
        db,
        holding,
        start=date(2026, 1, 1),
    )


def test_partial_patch_hydrates_existing_group_and_labels(client, user, db):
    source = _source(user.id, name="기존")
    label = _label(user.id)
    holding = _holding(user.id)
    tx, _ = _buy(holding, source=source, quantity="2", price="80000")
    _attach_label(tx, label)
    db.queue(
        _Result(one=holding.id),
        _Result(one=holding),
        _Result(many=[source]),
        _Result(many=[label]),
    )

    with patch("app.routers.transactions.rebuild_holding_snapshots", new=AsyncMock()):
        response = client.patch(
            f"/api/transactions/{tx.id}",
            json={"price": "85000"},
        )

    assert response.status_code == 200
    assert response.json()["source_group_name"] == "기존"
    assert response.json()["label_names"] == ["장기"]


def test_label_only_patch_hydrates_existing_group(client, user, db):
    source = _source(user.id, name="기존")
    old_label = _label(user.id, name="이전")
    new_label = _label(user.id, name="신규")
    holding = _holding(user.id)
    tx, _ = _buy(holding, source=source, quantity="2", price="80000")
    _attach_label(tx, old_label)
    db.queue(
        _Result(one=holding.id),
        _Result(one=holding),
        _Result(many=[new_label]),
        _Result(many=[source]),
        _Result(many=[new_label]),
    )

    with patch("app.routers.transactions.rebuild_holding_snapshots", new=AsyncMock()):
        response = client.patch(
            f"/api/transactions/{tx.id}",
            json={"label_ids": [str(new_label.id)]},
        )

    assert response.status_code == 200
    assert response.json()["source_group_name"] == "기존"
    assert response.json()["label_ids"] == [str(new_label.id)]
    assert response.json()["label_names"] == ["신규"]


def test_sell_quantity_patch_is_rejected(client, user, db):
    source = _source(user.id)
    holding = _holding(user.id)
    _, lot = _buy(holding, source=source)
    sell = _sell(holding, lot, source=source)
    db.queue(_Result(one=holding.id), _Result(one=holding))

    response = client.patch(
        f"/api/transactions/{sell.id}",
        json={"quantity": "2"},
    )

    assert response.status_code == 409
    assert sell.quantity == Decimal("1")


def test_sell_deposit_principal_flow_is_rejected(client, user, db):
    source = _source(user.id)
    holding = _holding(user.id)
    _, lot = _buy(holding, source=source)
    sell = _sell(holding, lot, source=source)
    db.queue(_Result(one=holding.id), _Result(one=holding))

    response = client.patch(
        f"/api/transactions/{sell.id}",
        json={"principal_flow": "DEPOSIT"},
    )

    assert response.status_code == 422
    assert sell.principal_flow == PrincipalFlow.REINVEST


def test_delete_buy_rejects_when_later_sell_would_become_invalid(client, user, db):
    holding = _holding(user.id)
    buy, lot = _buy(holding)
    _sell(holding, lot)
    db.queue(_Result(one=holding.id), _Result(one=holding))

    response = client.delete(f"/api/transactions/{buy.id}")

    assert response.status_code == 409
    assert "매도 배분" in response.json()["detail"]
    assert db.deleted == []
