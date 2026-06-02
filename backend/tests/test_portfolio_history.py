from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.database import get_db
from app.models.holding import Currency, TransactionType
from app.routers.deps import get_current_user
from app.routers.portfolio import (
    HistoricalPosition,
    _apply_transaction,
    _build_portfolio_history,
    _holdings_query,
    _owned_tag_query,
    get_portfolio_history,
    router,
)


def _tx(
    type_: TransactionType,
    quantity: str,
    price: str,
    transaction_date: date,
    *,
    created_at: datetime | None = None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        type=type_,
        quantity=Decimal(quantity),
        price=Decimal(price),
        transaction_date=transaction_date,
        created_at=created_at or datetime.combine(transaction_date, datetime.min.time()),
    )


def _snapshot(snapshot_date: date, close_price: str, *, stale_total_value: str = "0"):
    return SimpleNamespace(
        snapshot_date=snapshot_date,
        close_price=Decimal(close_price),
        total_value=Decimal(stale_total_value),
    )


def _holding(currency: Currency, transactions, snapshots):
    return SimpleNamespace(currency=currency, transactions=transactions, snapshots=snapshots)


class TestApplyTransaction:
    def test_uses_moving_average_cost_after_sell_and_new_buy(self):
        position = HistoricalPosition()
        position = _apply_transaction(position, _tx(TransactionType.BUY, "10", "100", date(2024, 1, 1)))
        position = _apply_transaction(position, _tx(TransactionType.BUY, "10", "200", date(2024, 1, 2)))
        position = _apply_transaction(position, _tx(TransactionType.SELL, "15", "999", date(2024, 1, 3)))
        position = _apply_transaction(position, _tx(TransactionType.BUY, "5", "300", date(2024, 1, 4)))

        assert position.quantity == Decimal("10")
        assert position.avg_cost == Decimal("225")
        assert position.cost_basis == Decimal("2250")

    def test_resets_average_cost_after_full_sell(self):
        position = _apply_transaction(
            HistoricalPosition(),
            _tx(TransactionType.BUY, "10", "100", date(2024, 1, 1)),
        )
        position = _apply_transaction(position, _tx(TransactionType.SELL, "10", "500", date(2024, 1, 2)))
        position = _apply_transaction(position, _tx(TransactionType.BUY, "2", "300", date(2024, 1, 3)))

        assert position.quantity == Decimal("2")
        assert position.avg_cost == Decimal("300")

    def test_raises_for_oversell(self):
        with pytest.raises(ValueError, match="exceeds available"):
            _apply_transaction(
                HistoricalPosition(),
                _tx(TransactionType.SELL, "1", "100", date(2024, 1, 1)),
            )


class TestBuildPortfolioHistory:
    def test_recomputes_daily_value_and_cost_basis_from_transactions(self):
        holding = _holding(
            Currency.KRW,
            [
                _tx(TransactionType.BUY, "10", "100", date(2024, 1, 1)),
                _tx(TransactionType.SELL, "4", "999", date(2024, 1, 3)),
                _tx(TransactionType.BUY, "2", "300", date(2024, 1, 4)),
            ],
            [
                _snapshot(date(2024, 1, 2), "120", stale_total_value="999999"),
                _snapshot(date(2024, 1, 3), "130", stale_total_value="999999"),
                _snapshot(date(2024, 1, 4), "140", stale_total_value="999999"),
            ],
        )

        result = _build_portfolio_history([holding])

        assert [point.model_dump() for point in result.series[Currency.KRW]] == [
            {
                "snapshot_date": date(2024, 1, 2),
                "total_value": Decimal("1200"),
                "total_cost_basis": Decimal("1000"),
            },
            {
                "snapshot_date": date(2024, 1, 3),
                "total_value": Decimal("780"),
                "total_cost_basis": Decimal("600"),
            },
            {
                "snapshot_date": date(2024, 1, 4),
                "total_value": Decimal("1120"),
                "total_cost_basis": Decimal("1200"),
            },
        ]

    def test_keeps_krw_and_usd_series_separate(self):
        snapshot_date = date(2024, 1, 2)
        holdings = [
            _holding(
                Currency.KRW,
                [_tx(TransactionType.BUY, "2", "1000", date(2024, 1, 1))],
                [_snapshot(snapshot_date, "1100")],
            ),
            _holding(
                Currency.USD,
                [_tx(TransactionType.BUY, "3", "10", date(2024, 1, 1))],
                [_snapshot(snapshot_date, "12")],
            ),
        ]

        result = _build_portfolio_history(holdings)

        assert result.series[Currency.KRW][0].total_value == Decimal("2200")
        assert result.series[Currency.KRW][0].total_cost_basis == Decimal("2000")
        assert result.series[Currency.USD][0].total_value == Decimal("36")
        assert result.series[Currency.USD][0].total_cost_basis == Decimal("30")

    def test_adds_same_currency_holdings_on_the_same_day(self):
        snapshot_date = date(2024, 1, 2)
        holdings = [
            _holding(
                Currency.USD,
                [_tx(TransactionType.BUY, "2", "10", date(2024, 1, 1))],
                [_snapshot(snapshot_date, "12")],
            ),
            _holding(
                Currency.USD,
                [_tx(TransactionType.BUY, "4", "20", date(2024, 1, 1))],
                [_snapshot(snapshot_date, "25")],
            ),
        ]

        result = _build_portfolio_history(holdings)

        assert result.series[Currency.USD][0].total_value == Decimal("124")
        assert result.series[Currency.USD][0].total_cost_basis == Decimal("100")

    def test_raises_for_oversell_after_latest_snapshot(self):
        holding = _holding(
            Currency.KRW,
            [
                _tx(TransactionType.BUY, "1", "100", date(2024, 1, 1)),
                _tx(TransactionType.SELL, "2", "100", date(2024, 1, 3)),
            ],
            [_snapshot(date(2024, 1, 2), "110")],
        )

        with pytest.raises(ValueError, match="exceeds available"):
            _build_portfolio_history([holding])

    def test_orders_same_day_transactions_by_creation_time(self):
        transaction_date = date(2024, 1, 1)
        created_at = datetime(2024, 1, 1, 12, 0)
        holding = _holding(
            Currency.KRW,
            [
                _tx(TransactionType.SELL, "1", "200", transaction_date, created_at=created_at + timedelta(seconds=1)),
                _tx(TransactionType.BUY, "1", "100", transaction_date, created_at=created_at),
            ],
            [_snapshot(transaction_date, "150")],
        )

        result = _build_portfolio_history([holding])

        assert result.series[Currency.KRW][0].total_value == Decimal("0")
        assert result.series[Currency.KRW][0].total_cost_basis == Decimal("0")


class TestPortfolioQueries:
    def test_owned_tag_query_checks_user_id(self):
        query = str(_owned_tag_query(uuid.uuid4(), uuid.uuid4()))

        assert "tags.id" in query
        assert "tags.user_id" in query

    def test_filtered_holdings_query_checks_holding_owner_and_tag(self):
        query = str(_holdings_query(uuid.uuid4(), uuid.uuid4()))

        assert "holdings.user_id" in query
        assert "holding_tags.tag_id" in query


@pytest.mark.asyncio
async def test_history_endpoint_rejects_non_owned_tag():
    db = AsyncMock()
    tag_result = MagicMock()
    tag_result.scalar_one_or_none.return_value = None
    db.execute.return_value = tag_result

    with pytest.raises(HTTPException) as exc_info:
        await get_portfolio_history(
            tag_id=uuid.uuid4(),
            current_user=SimpleNamespace(id=uuid.uuid4()),
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Tag not found"


def test_history_endpoint_requires_authentication():
    app = FastAPI()
    app.include_router(router)

    async def _unauthenticated_user():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    async def _unused_db():
        yield MagicMock()

    app.dependency_overrides[get_current_user] = _unauthenticated_user
    app.dependency_overrides[get_db] = _unused_db

    response = TestClient(app).get("/api/portfolio/history")

    assert response.status_code == 401
