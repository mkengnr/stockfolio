import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.models.group import BuyLot, Label, SellLotAllocation, SourceGroup, TransactionLabel
from app.models.holding import Currency, Holding, Market, PrincipalFlow, Transaction, TransactionType
from app.routers.deps import get_current_user
from app.routers.holdings import _rebuild_snapshots_after_mutation, _replay_and_update_lots, router
from app.schemas.holding import HoldingCreateIn, TransactionIn


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
        self.added = []
        self.deleted = []

    def queue(self, *results):
        self.results.extend(results)

    async def execute(self, _query):
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
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    async def _user():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


def _source(user_id, *, name="월급", color="#6366f1"):
    return SourceGroup(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        color=color,
        share_requires_auth=True,
        created_at=NOW,
    )


def _label(user_id):
    return Label(
        id=uuid.uuid4(),
        user_id=user_id,
        name="장기",
        color="#6366f1",
        share_requires_auth=True,
        created_at=NOW,
    )


def _holding(user_id):
    return Holding(
        id=uuid.uuid4(),
        user_id=user_id,
        ticker="005930",
        market=Market.KRX,
        name="삼성전자",
        quantity=Decimal("0"),
        avg_price=Decimal("0"),
        currency=Currency.KRW,
        first_buy_date=date(2026, 1, 1),
        is_active=True,
        created_at=NOW,
        transactions=[],
        buy_lots=[],
    )


def _buy(
    holding,
    *,
    source_group_id=None,
    quantity="2",
    price="80000",
    principal_flow=PrincipalFlow.DEPOSIT,
    transaction_date=date(2026, 1, 1),
):
    tx = Transaction(
        id=uuid.uuid4(),
        holding_id=holding.id,
        user_id=holding.user_id,
        source_group_id=source_group_id,
        type=TransactionType.BUY,
        quantity=Decimal(quantity),
        price=Decimal(price),
        transaction_date=transaction_date,
        principal_flow=principal_flow,
        created_at=NOW,
        transaction_labels=[],
        sell_allocations=[],
    )
    lot = BuyLot(
        id=uuid.uuid4(),
        transaction_id=tx.id,
        holding_id=holding.id,
        user_id=holding.user_id,
        source_group_id=source_group_id,
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
    source_group_id=None,
    quantity="1",
    price="100000",
    principal_flow=PrincipalFlow.REINVEST,
):
    tx = Transaction(
        id=uuid.uuid4(),
        holding_id=holding.id,
        user_id=holding.user_id,
        source_group_id=source_group_id,
        type=TransactionType.SELL,
        quantity=Decimal(quantity),
        price=Decimal(price),
        principal_flow=principal_flow,
        transaction_date=date(2026, 2, 1),
        created_at=NOW,
        requires_review=False,
        transaction_labels=[],
        sell_allocations=[],
    )
    allocation = SellLotAllocation(
        id=uuid.uuid4(),
        sell_transaction_id=tx.id,
        buy_lot_id=lot.id,
        quantity=Decimal(quantity),
    )
    tx.sell_allocations.append(allocation)
    holding.transactions.append(tx)
    holding.quantity -= tx.quantity
    lot.remaining_quantity -= tx.quantity
    return tx


def _legacy_sell_requiring_review(holding, *, quantity="1"):
    tx = Transaction(
        id=uuid.uuid4(),
        holding_id=holding.id,
        user_id=holding.user_id,
        type=TransactionType.SELL,
        quantity=Decimal(quantity),
        price=Decimal("100000"),
        transaction_date=date(2026, 2, 1),
        created_at=NOW,
        requires_review=True,
        transaction_labels=[],
        sell_allocations=[],
    )
    holding.transactions.append(tx)
    return tx


def test_existing_payloads_remain_valid_and_unclassified():
    create = HoldingCreateIn(
        ticker="005930",
        quantity="1",
        price="80000",
        transaction_date="2026-01-01",
    )
    tx = TransactionIn(
        type="BUY",
        quantity="1",
        price="80000",
        transaction_date="2026-01-01",
    )

    assert create.source_group_id is None
    assert create.principal_flow == "DEPOSIT"
    assert create.label_ids == []
    assert tx.source_group_id is None
    assert tx.principal_flow == "DEPOSIT"
    assert tx.label_ids == []
    assert tx.sell_allocations == []


@pytest.mark.asyncio
async def test_snapshot_rebuild_failure_is_returned_as_service_unavailable(user, db):
    holding = _holding(user.id)

    with patch(
        "app.routers.holdings.rebuild_holding_snapshots",
        new=AsyncMock(side_effect=RuntimeError("provider unavailable")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _rebuild_snapshots_after_mutation(db, holding, start=date(2026, 1, 1))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Price history rebuild failed; retry the transaction"


def test_create_holding_creates_initial_unclassified_buy_lot(client, db):
    db.queue(_Result())

    with (
        patch(
            "app.routers.holdings.stock_fetcher.get_current_price",
            return_value=SimpleNamespace(name="삼성전자"),
        ),
        patch("app.routers.holdings.backfill_holding_snapshots", new=AsyncMock()),
    ):
        response = client.post(
            "/api/holdings",
            json={
                "ticker": "005930",
                "quantity": "1",
                "price": "80000",
                "transaction_date": "2026-01-01",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["transactions"][0]["source_group_id"] is None
    assert payload["transactions"][0]["principal_flow"] == "DEPOSIT"
    assert payload["transactions"][0]["buy_lot"]["remaining_quantity"] == "1"
    assert any(isinstance(entity, BuyLot) for entity in db.added)


def test_get_holding_returns_performance_and_group_breakdown(client, user, db):
    source_one = _source(user.id, name="모음통장", color="#2563eb")
    source_two = _source(user.id, name="긴급통장", color="#dc2626")
    holding = _holding(user.id)
    _, lot_one = _buy(
        holding,
        source_group_id=source_one.id,
        quantity="2",
        price="80000",
        transaction_date=date(2026, 1, 1),
    )
    _sell(
        holding,
        lot_one,
        source_group_id=source_one.id,
        quantity="1",
        price="90000",
        principal_flow=PrincipalFlow.WITHDRAW,
    )
    _buy(
        holding,
        source_group_id=source_two.id,
        quantity="1",
        price="100000",
        transaction_date=date(2026, 1, 2),
    )
    db.queue(_Result(one=holding), _Result(many=[source_one, source_two]))

    with patch(
        "app.routers.holdings.get_price",
        new=AsyncMock(return_value=SimpleNamespace(price=Decimal("120000"))),
    ):
        response = client.get(f"/api/holdings/{holding.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["performance"] == {
        "total_invested_principal": "170000",
        "remaining_cost_basis": "180000",
        "current_value": "240000",
        "profit_loss": "70000",
        "profit_loss_pct": "41.17647058823529411764705882",
    }
    assert payload["group_breakdown"] == [
        {
            "source_group_id": str(source_two.id),
            "name": "긴급통장",
            "color": "#dc2626",
            "remaining_quantity": "1",
            "invested_principal": "100000",
            "remaining_cost_basis": "100000",
            "current_value": "120000",
            "profit_loss": "20000",
            "profit_loss_pct": "20.0",
        },
        {
            "source_group_id": str(source_one.id),
            "name": "모음통장",
            "color": "#2563eb",
            "remaining_quantity": "1",
            "invested_principal": "70000",
            "remaining_cost_basis": "80000",
            "current_value": "120000",
            "profit_loss": "50000",
            "profit_loss_pct": "71.42857142857142857142857143",
        },
    ]


def test_get_holding_nulls_performance_when_lot_accounting_requires_review(client, user, db):
    holding = _holding(user.id)
    _buy(holding, quantity="2", price="80000")
    _legacy_sell_requiring_review(holding, quantity="1")
    db.queue(_Result(one=holding))

    with patch(
        "app.routers.holdings.get_price",
        new=AsyncMock(return_value=SimpleNamespace(price=Decimal("120000"))),
    ):
        response = client.get(f"/api/holdings/{holding.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["performance"] is None
    assert payload["group_breakdown"] == []


def test_get_holding_keeps_principal_metrics_when_current_price_is_unavailable(client, user, db):
    source = _source(user.id, name="모음통장", color="#2563eb")
    holding = _holding(user.id)
    _buy(
        holding,
        source_group_id=source.id,
        quantity="2",
        price="80000",
        transaction_date=date(2026, 1, 1),
    )
    db.queue(_Result(one=holding), _Result(many=[source]))

    with patch("app.routers.holdings.get_price", new=AsyncMock(side_effect=RuntimeError("price unavailable"))):
        response = client.get(f"/api/holdings/{holding.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["performance"] == {
        "total_invested_principal": "160000",
        "remaining_cost_basis": "160000",
        "current_value": None,
        "profit_loss": None,
        "profit_loss_pct": None,
    }
    assert payload["group_breakdown"][0]["invested_principal"] == "160000"
    assert payload["group_breakdown"][0]["remaining_cost_basis"] == "160000"
    assert payload["group_breakdown"][0]["current_value"] is None
    assert payload["group_breakdown"][0]["profit_loss"] is None
    assert payload["group_breakdown"][0]["profit_loss_pct"] is None


def test_create_holding_rejects_ticker_when_provider_lookup_fails(client, db):
    db.queue(_Result())

    with patch("app.routers.holdings.stock_fetcher.get_current_price", side_effect=RuntimeError):
        response = client.post(
            "/api/holdings",
            json={
                "ticker": "NOTREAL",
                "quantity": "1",
                "price": "80000",
                "transaction_date": "2026-01-01",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Ticker could not be verified"
    assert db.added == []


def test_add_buy_creates_classified_lot_and_labels(client, user, db):
    holding = _holding(user.id)
    source = _source(user.id)
    label = _label(user.id)
    db.queue(_Result(one=holding), _Result(many=[source.id]), _Result(many=[label.id]))

    with patch("app.routers.holdings.rebuild_holding_snapshots", new=AsyncMock()):
        response = client.post(
            f"/api/holdings/{holding.id}/transactions",
            json={
                "type": "BUY",
                "quantity": "2",
                "price": "80000",
                "transaction_date": "2026-01-01",
                "source_group_id": str(source.id),
                "label_ids": [str(label.id)],
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_group_id"] == str(source.id)
    assert payload["label_ids"] == [str(label.id)]
    assert payload["buy_lot"]["remaining_quantity"] == "2"
    assert payload["buy_lot"]["label_ids"] == [str(label.id)]
    assert any(isinstance(entity, BuyLot) for entity in db.added)
    assert any(isinstance(entity, TransactionLabel) for entity in db.added)


def test_sell_persists_selected_allocations_and_updates_remaining(client, user, db):
    holding = _holding(user.id)
    source = _source(user.id)
    _, lot = _buy(holding, source_group_id=source.id)
    db.queue(_Result(one=holding), _Result(many=[source.id]), _Result(many=[lot.id]))

    with patch("app.routers.holdings.rebuild_holding_snapshots", new=AsyncMock()):
        response = client.post(
            f"/api/holdings/{holding.id}/transactions",
            json={
                "type": "SELL",
                "quantity": "1",
                "price": "100000",
                "transaction_date": "2026-02-01",
                "source_group_id": str(source.id),
                "sell_allocations": [{"buy_lot_id": str(lot.id), "quantity": "1"}],
            },
        )

    assert response.status_code == 201
    assert response.json()["sell_allocations"] == [
        {"buy_lot_id": str(lot.id), "quantity": "1"}
    ]
    assert lot.remaining_quantity == Decimal("1")
    assert any(isinstance(entity, SellLotAllocation) for entity in db.added)


def test_sell_rejects_quantity_above_selected_lot_remaining(client, user, db):
    holding = _holding(user.id)
    source = _source(user.id)
    _, lot = _buy(holding, source_group_id=source.id, quantity="1")
    db.queue(_Result(one=holding), _Result(many=[source.id]), _Result(many=[lot.id]))

    response = client.post(
        f"/api/holdings/{holding.id}/transactions",
        json={
            "type": "SELL",
            "quantity": "2",
            "price": "100000",
            "transaction_date": "2026-02-01",
            "source_group_id": str(source.id),
            "sell_allocations": [{"buy_lot_id": str(lot.id), "quantity": "2"}],
        },
    )

    assert response.status_code == 422
    assert lot.remaining_quantity == Decimal("1")


def test_sell_requires_explicit_allocations(client, user, db):
    holding = _holding(user.id)
    source = _source(user.id)
    _buy(holding, source_group_id=source.id)
    db.queue(_Result(one=holding), _Result(many=[source.id]))

    response = client.post(
        f"/api/holdings/{holding.id}/transactions",
        json={
            "type": "SELL",
            "quantity": "1",
            "price": "100000",
            "transaction_date": "2026-02-01",
            "source_group_id": str(source.id),
        },
    )

    assert response.status_code == 422


def test_lots_endpoint_lists_only_available_lots_in_source(client, user, db):
    holding = _holding(user.id)
    source = _source(user.id)
    _, available = _buy(holding, source_group_id=source.id)
    _, depleted = _buy(holding, source_group_id=source.id)
    depleted.remaining_quantity = Decimal("0")
    db.queue(_Result(one=holding), _Result(many=[source.id]), _Result(many=[available]))

    response = client.get(
        f"/api/holdings/{holding.id}/lots",
        params={"scope_kind": "source", "scope_id": str(source.id)},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(available.id)]


def test_lots_endpoint_validates_scope_shape(client, user, db):
    holding = _holding(user.id)
    db.queue(_Result(one=holding))

    response = client.get(
        f"/api/holdings/{holding.id}/lots",
        params={"scope_kind": "unclassified", "scope_id": str(uuid.uuid4())},
    )

    assert response.status_code == 422


def test_lots_endpoint_lists_unclassified_available_lots(client, user, db):
    holding = _holding(user.id)
    tx, available = _buy(holding)
    label = _label(user.id)
    tx.transaction_labels.append(TransactionLabel(transaction_id=tx.id, label_id=label.id))
    db.queue(_Result(one=holding), _Result(many=[available]))

    response = client.get(
        f"/api/holdings/{holding.id}/lots",
        params={"scope_kind": "unclassified"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(available.id)]
    assert response.json()[0]["label_ids"] == [str(label.id)]


def test_review_lots_endpoint_lists_lots_available_before_legacy_sell(client, user, db):
    holding = _holding(user.id)
    _, lot = _buy(holding)
    legacy_sell = _legacy_sell_requiring_review(holding)
    lot.remaining_quantity = Decimal("999")
    db.queue(_Result(one=holding))

    response = client.get(
        f"/api/holdings/{holding.id}/transactions/{legacy_sell.id}/review-lots",
        params={"scope_kind": "unclassified"},
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(lot.id)
    assert response.json()[0]["remaining_quantity"] == "2"


def test_repair_legacy_sell_persists_allocations_and_clears_review(client, user, db):
    holding = _holding(user.id)
    _, lot = _buy(holding)
    legacy_sell = _legacy_sell_requiring_review(holding)
    db.queue(_Result(one=holding), _Result(many=[lot.id]))

    with patch("app.routers.holdings.rebuild_holding_snapshots", new=AsyncMock()):
        response = client.patch(
            f"/api/holdings/{holding.id}/transactions/{legacy_sell.id}/review",
            json={
                "source_group_id": None,
                "label_ids": [],
                "sell_allocations": [{"buy_lot_id": str(lot.id), "quantity": "1"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["requires_review"] is False
    assert response.json()["sell_allocations"] == [
        {"buy_lot_id": str(lot.id), "quantity": "1"}
    ]
    assert legacy_sell.requires_review is False
    assert lot.remaining_quantity == Decimal("1")
    assert any(isinstance(entity, SellLotAllocation) for entity in db.added)


def test_repair_legacy_sell_requires_oldest_unresolved_sell_first(client, user, db):
    holding = _holding(user.id)
    _, lot = _buy(holding, quantity="3")
    _legacy_sell_requiring_review(holding)
    later_sell = _legacy_sell_requiring_review(holding)
    later_sell.transaction_date = date(2026, 3, 1)
    db.queue(_Result(one=holding))

    response = client.patch(
        f"/api/holdings/{holding.id}/transactions/{later_sell.id}/review",
        json={
            "source_group_id": None,
            "label_ids": [],
            "sell_allocations": [{"buy_lot_id": str(lot.id), "quantity": "1"}],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Resolve earlier reviewed sells first"
    assert later_sell.requires_review is True
    assert db.added == []


def test_buy_classification_updates_lot_source_and_replaces_labels(client, user, db):
    holding = _holding(user.id)
    tx, lot = _buy(holding)
    source = _source(user.id)
    label = _label(user.id)
    old_transaction_label = TransactionLabel(transaction_id=tx.id, label_id=uuid.uuid4())
    tx.transaction_labels.append(old_transaction_label)
    db.queue(
        _Result(one=holding),
        _Result(one=tx),
        _Result(many=[source.id]),
        _Result(many=[label.id]),
    )

    response = client.patch(
        f"/api/holdings/{holding.id}/transactions/{tx.id}/classification",
        json={"source_group_id": str(source.id), "label_ids": [str(label.id)]},
    )

    assert response.status_code == 200
    assert tx.source_group_id == source.id
    assert lot.source_group_id == source.id
    assert response.json()["label_ids"] == [str(label.id)]
    assert db.deleted == [old_transaction_label]


def test_buy_classification_preserves_existing_requested_label(client, user, db):
    holding = _holding(user.id)
    tx, _ = _buy(holding)
    label = _label(user.id)
    existing_transaction_label = TransactionLabel(transaction_id=tx.id, label_id=label.id)
    tx.transaction_labels.append(existing_transaction_label)
    db.queue(
        _Result(one=holding),
        _Result(one=tx),
        _Result(many=[label.id]),
    )

    response = client.patch(
        f"/api/holdings/{holding.id}/transactions/{tx.id}/classification",
        json={"label_ids": [str(label.id)]},
    )

    assert response.status_code == 200
    assert tx.transaction_labels == [existing_transaction_label]
    assert db.deleted == []
    assert existing_transaction_label not in db.added


def test_sell_classification_rejects_source_that_does_not_match_allocated_lot(client, user, db):
    holding = _holding(user.id)
    source = _source(user.id)
    other_source = _source(user.id)
    _, lot = _buy(holding, source_group_id=source.id)
    sell = _sell(holding, lot, source_group_id=source.id)
    db.queue(_Result(one=holding), _Result(one=sell), _Result(many=[other_source.id]))

    response = client.patch(
        f"/api/holdings/{holding.id}/transactions/{sell.id}/classification",
        json={"source_group_id": str(other_source.id), "label_ids": []},
    )

    assert response.status_code == 422
    assert sell.source_group_id == source.id


def test_delete_buy_rejects_when_later_sell_would_become_invalid(client, user, db):
    holding = _holding(user.id)
    buy, lot = _buy(holding)
    _sell(holding, lot)
    db.queue(_Result(one=buy), _Result(one=holding))

    response = client.delete(f"/api/holdings/{holding.id}/transactions/{buy.id}")

    assert response.status_code == 422
    assert db.deleted == []


def test_delete_sell_replays_lots_and_rebuilds_snapshots(client, user, db):
    holding = _holding(user.id)
    _, lot = _buy(holding)
    sell = _sell(holding, lot)
    db.queue(_Result(one=sell), _Result(one=holding))

    with patch("app.routers.holdings.rebuild_holding_snapshots", new=AsyncMock()) as rebuild:
        response = client.delete(f"/api/holdings/{holding.id}/transactions/{sell.id}")

    assert response.status_code == 204
    assert lot.remaining_quantity == Decimal("2")
    assert db.deleted == [sell]
    assert sell not in holding.transactions
    rebuild.assert_awaited_once_with(db, holding, start=sell.transaction_date)


def test_delete_earliest_buy_invalidates_old_snapshots_and_regenerates_from_next_buy(client, user, db):
    holding = _holding(user.id)
    first_buy, _ = _buy(holding, transaction_date=date(2026, 1, 1))
    _buy(holding, transaction_date=date(2026, 2, 1))
    db.queue(_Result(one=first_buy), _Result(one=holding))

    with patch("app.routers.holdings.rebuild_holding_snapshots", new=AsyncMock()) as rebuild:
        response = client.delete(f"/api/holdings/{holding.id}/transactions/{first_buy.id}")

    assert response.status_code == 204
    assert holding.first_buy_date == date(2026, 2, 1)
    rebuild.assert_awaited_once_with(
        db,
        holding,
        start=date(2026, 2, 1),
        invalidate_start=date(2026, 1, 1),
    )


def test_delete_only_buy_invalidates_snapshots_without_regeneration(client, user, db):
    holding = _holding(user.id)
    buy, _ = _buy(holding)
    db.queue(_Result(one=buy), _Result(one=holding))

    with patch("app.routers.holdings.rebuild_holding_snapshots", new=AsyncMock()) as rebuild:
        response = client.delete(f"/api/holdings/{holding.id}/transactions/{buy.id}")

    assert response.status_code == 204
    rebuild.assert_awaited_once_with(
        db,
        holding,
        start=None,
        invalidate_start=buy.transaction_date,
    )


def test_delete_holding_rejects_positive_lot_quantity(client, user, db):
    holding = _holding(user.id)
    _buy(holding)
    db.queue(_Result(one=holding), _Result(one=Decimal("2")))

    response = client.delete(f"/api/holdings/{holding.id}")

    assert response.status_code == 409
    assert holding.is_active is True


def test_cross_user_source_is_hidden_on_transaction_mutation(client, user, db):
    holding = _holding(user.id)
    db.queue(_Result(one=holding), _Result(many=[]))

    response = client.post(
        f"/api/holdings/{holding.id}/transactions",
        json={
            "type": "BUY",
            "quantity": "1",
            "price": "80000",
            "transaction_date": "2026-01-01",
            "source_group_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 404


def test_cross_user_label_is_hidden_on_transaction_mutation(client, user, db):
    holding = _holding(user.id)
    db.queue(_Result(one=holding), _Result(many=[]))

    response = client.post(
        f"/api/holdings/{holding.id}/transactions",
        json={
            "type": "BUY",
            "quantity": "1",
            "price": "80000",
            "transaction_date": "2026-01-01",
            "label_ids": [str(uuid.uuid4())],
        },
    )

    assert response.status_code == 404


def test_cross_user_buy_lot_is_hidden_on_sell(client, user, db):
    holding = _holding(user.id)
    source = _source(user.id)
    db.queue(_Result(one=holding), _Result(many=[source.id]), _Result(many=[]))

    response = client.post(
        f"/api/holdings/{holding.id}/transactions",
        json={
            "type": "SELL",
            "quantity": "1",
            "price": "100000",
            "transaction_date": "2026-02-01",
            "source_group_id": str(source.id),
            "sell_allocations": [{"buy_lot_id": str(uuid.uuid4()), "quantity": "1"}],
        },
    )

    assert response.status_code == 404


def test_replay_rejects_unresolved_legacy_sell_before_updating_lot_mirrors(user):
    holding = _holding(user.id)
    _, lot = _buy(holding)
    _legacy_sell_requiring_review(holding)
    lot.remaining_quantity = Decimal("999")

    with pytest.raises(HTTPException) as exc_info:
        _replay_and_update_lots(holding)

    assert exc_info.value.status_code == 409
    assert lot.remaining_quantity == Decimal("999")


def test_add_transaction_rejects_unresolved_legacy_sell_before_appending(client, user, db):
    holding = _holding(user.id)
    _buy(holding)
    _legacy_sell_requiring_review(holding)
    original_transactions = list(holding.transactions)
    db.queue(_Result(one=holding))

    response = client.post(
        f"/api/holdings/{holding.id}/transactions",
        json={
            "type": "BUY",
            "quantity": "1",
            "price": "80000",
            "transaction_date": "2026-03-01",
        },
    )

    assert response.status_code == 409
    assert holding.transactions == original_transactions
    assert db.added == []


def test_lots_endpoint_rejects_unresolved_legacy_sell(client, user, db):
    holding = _holding(user.id)
    _, lot = _buy(holding)
    _legacy_sell_requiring_review(holding)
    db.queue(_Result(one=holding), _Result(many=[lot]))

    response = client.get(
        f"/api/holdings/{holding.id}/lots",
        params={"scope_kind": "unclassified"},
    )

    assert response.status_code == 409


def test_classification_rejects_unresolved_legacy_sell(client, user, db):
    holding = _holding(user.id)
    buy, _ = _buy(holding)
    _legacy_sell_requiring_review(holding)
    db.queue(_Result(one=holding), _Result(one=buy))

    response = client.patch(
        f"/api/holdings/{holding.id}/transactions/{buy.id}/classification",
        json={"label_ids": []},
    )

    assert response.status_code == 409


def test_delete_transaction_rejects_unresolved_legacy_sell(client, user, db):
    holding = _holding(user.id)
    first_buy, _ = _buy(holding)
    _buy(holding, transaction_date=date(2026, 1, 2))
    _legacy_sell_requiring_review(holding)
    db.queue(_Result(one=first_buy), _Result(one=holding))

    response = client.delete(f"/api/holdings/{holding.id}/transactions/{first_buy.id}")

    assert response.status_code == 409
    assert db.deleted == []


def test_add_transaction_rejects_inactive_holding(client, user, db):
    holding = _holding(user.id)
    holding.is_active = False
    db.queue(_Result(one=holding))

    response = client.post(
        f"/api/holdings/{holding.id}/transactions",
        json={
            "type": "BUY",
            "quantity": "1",
            "price": "80000",
            "transaction_date": "2026-01-01",
        },
    )

    assert response.status_code == 409
    assert db.added == []


def test_cross_user_transaction_is_hidden_on_classification(client, user, db):
    holding = _holding(user.id)
    _buy(holding)
    db.queue(_Result(one=holding), _Result())

    response = client.patch(
        f"/api/holdings/{holding.id}/transactions/{uuid.uuid4()}/classification",
        json={"label_ids": []},
    )

    assert response.status_code == 404


def test_cross_user_transaction_is_hidden_on_delete(client, db):
    db.queue(_Result())

    response = client.delete(f"/api/holdings/{uuid.uuid4()}/transactions/{uuid.uuid4()}")

    assert response.status_code == 404
