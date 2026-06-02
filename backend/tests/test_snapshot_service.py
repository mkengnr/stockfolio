from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.models.holding import TransactionType
from app.services.snapshot_service import (
    _build_snapshot_values,
    backfill_holding_snapshots,
    rebuild_holding_snapshots,
)
from app.services.stock_fetcher import OHLCBar


def _tx(type_: TransactionType, quantity: str, transaction_date: date):
    return SimpleNamespace(
        type=type_,
        quantity=Decimal(quantity),
        transaction_date=transaction_date,
        created_at=None,
    )


def _bar(snapshot_date: date, close: str):
    price = Decimal(close)
    return OHLCBar(
        date=snapshot_date,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=0,
    )


def test_build_snapshot_values_uses_historical_quantity():
    values = _build_snapshot_values(
        [
            _tx(TransactionType.BUY, "10", date(2024, 1, 2)),
            _tx(TransactionType.SELL, "4", date(2024, 1, 4)),
        ],
        [
            _bar(date(2024, 1, 2), "100"),
            _bar(date(2024, 1, 3), "110"),
            _bar(date(2024, 1, 4), "120"),
        ],
    )

    assert [(value.snapshot_date, value.total_value) for value in values] == [
        (date(2024, 1, 2), Decimal("1000")),
        (date(2024, 1, 3), Decimal("1100")),
        (date(2024, 1, 4), Decimal("720")),
    ]


@pytest.mark.asyncio
async def test_backfill_adds_only_missing_dates():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    existing_result = MagicMock()
    existing_result.scalars.return_value.all.return_value = [date(2024, 1, 3)]
    db.execute.return_value = existing_result
    holding = SimpleNamespace(
        id="holding-id",
        ticker="005930",
        first_buy_date=date(2024, 1, 2),
        transactions=[_tx(TransactionType.BUY, "10", date(2024, 1, 2))],
    )

    with patch(
        "app.services.snapshot_service.stock_fetcher.get_price_history",
        return_value=[
            _bar(date(2024, 1, 2), "100"),
            _bar(date(2024, 1, 3), "110"),
        ],
    ):
        added = await backfill_holding_snapshots(db, holding, end=date(2024, 1, 3))

    assert added == 1
    db.add.assert_called_once()
    snapshot = db.add.call_args.args[0]
    assert snapshot.snapshot_date == date(2024, 1, 2)
    assert snapshot.close_price == Decimal("100")
    assert snapshot.total_value == Decimal("1000")
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_rebuild_fetches_values_before_invalidating_derived_snapshots():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    holding = SimpleNamespace(
        id=uuid.uuid4(),
        ticker="005930",
        transactions=[_tx(TransactionType.BUY, "10", date(2024, 1, 4))],
    )

    with patch(
        "app.services.snapshot_service.stock_fetcher.get_price_history",
        return_value=[_bar(date(2024, 1, 4), "100")],
    ):
        rebuilt = await rebuild_holding_snapshots(
            db,
            holding,
            start=date(2024, 1, 4),
            invalidate_start=date(2024, 1, 2),
            end=date(2024, 1, 4),
        )

    assert rebuilt == 1
    db.execute.assert_awaited_once()
    statement = db.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "daily_snapshots.snapshot_date >= '2024-01-02'" in compiled
    snapshot = db.add.call_args.args[0]
    assert snapshot.snapshot_date == date(2024, 1, 4)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_rebuild_does_not_delete_snapshots_when_history_fetch_fails():
    db = MagicMock()
    db.execute = AsyncMock()
    holding = SimpleNamespace(
        id=uuid.uuid4(),
        ticker="005930",
        transactions=[_tx(TransactionType.BUY, "10", date(2024, 1, 2))],
    )

    with (
        patch(
            "app.services.snapshot_service.stock_fetcher.get_price_history",
            side_effect=RuntimeError("provider unavailable"),
        ),
        pytest.raises(RuntimeError, match="provider unavailable"),
    ):
        await rebuild_holding_snapshots(db, holding, start=date(2024, 1, 2))

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_only_invalidates_when_no_buy_transactions_remain():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    holding = SimpleNamespace(
        id=uuid.uuid4(),
        ticker="005930",
        transactions=[],
    )

    with patch(
        "app.services.snapshot_service.stock_fetcher.get_price_history",
    ) as get_price_history:
        rebuilt = await rebuild_holding_snapshots(
            db,
            holding,
            start=None,
            invalidate_start=date(2024, 1, 2),
        )

    assert rebuilt == 0
    get_price_history.assert_not_called()
    db.execute.assert_awaited_once()
    db.add.assert_not_called()
    db.flush.assert_not_awaited()
