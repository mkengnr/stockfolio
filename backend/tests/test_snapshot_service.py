from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo
import uuid

import pytest

from app.models.holding import Currency, Market, TransactionType
from app.services import snapshot_service
from app.services.stock_fetcher import PriceResult
from app.services.snapshot_service import (
    _build_snapshot_values,
    backfill_holding_snapshots,
    backfill_recent_comparison_snapshots,
    rebuild_holding_snapshots,
)
from app.services.stock_fetcher import OHLCBar


def _tx(
    type_: TransactionType,
    quantity: str,
    transaction_date: date,
    *,
    transaction_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
):
    return SimpleNamespace(
        id=transaction_id or uuid.uuid4(),
        type=type_,
        quantity=Decimal(quantity),
        transaction_date=transaction_date,
        created_at=created_at,
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


def test_build_snapshot_values_skips_non_finite_close_bars():
    nan_bar = OHLCBar(
        date=date(2024, 1, 3),
        open=Decimal("NaN"),
        high=Decimal("NaN"),
        low=Decimal("NaN"),
        close=Decimal("NaN"),
        volume=0,
    )
    values = _build_snapshot_values(
        [_tx(TransactionType.BUY, "10", date(2024, 1, 2))],
        [_bar(date(2024, 1, 2), "100"), nan_bar, _bar(date(2024, 1, 4), "120")],
    )

    assert [value.snapshot_date for value in values] == [date(2024, 1, 2), date(2024, 1, 4)]


def test_build_snapshot_values_uses_transaction_id_to_break_creation_time_ties():
    transaction_date = date(2024, 1, 2)
    created_at = datetime(2024, 1, 2, 12, 0)

    values = _build_snapshot_values(
        [
            _tx(
                TransactionType.SELL,
                "1",
                transaction_date,
                transaction_id=uuid.UUID(int=2),
                created_at=created_at,
            ),
            _tx(
                TransactionType.BUY,
                "1",
                transaction_date,
                transaction_id=uuid.UUID(int=1),
                created_at=created_at,
            ),
        ],
        [_bar(transaction_date, "100")],
    )

    assert values[0].total_value == Decimal("0")


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
async def test_backfill_recent_comparison_snapshots_ends_before_current_price_date():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    existing_result = MagicMock()
    existing_result.scalars.return_value.all.return_value = [date(2026, 6, 5)]
    db.execute.return_value = existing_result
    holding = SimpleNamespace(
        id="holding-id",
        ticker="005930",
        first_buy_date=date(2026, 1, 2),
        transactions=[_tx(TransactionType.BUY, "10", date(2026, 1, 2))],
    )

    with patch(
        "app.services.snapshot_service.stock_fetcher.get_price_history",
        return_value=[
            _bar(date(2026, 6, 5), "100"),
            _bar(date(2026, 6, 8), "110"),
            _bar(date(2026, 6, 9), "120"),
        ],
    ) as get_price_history:
        added = await backfill_recent_comparison_snapshots(
            db,
            holding,
            current_price_date=date(2026, 6, 9),
        )

    assert added == 1
    get_price_history.assert_called_once_with(
        "005930",
        date(2026, 6, 1),
        date(2026, 6, 8),
    )
    snapshot = db.add.call_args.args[0]
    assert snapshot.snapshot_date == date(2026, 6, 8)
    assert snapshot.total_value == Decimal("1100")


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
async def test_rebuild_deletes_from_start_when_edit_moves_date_earlier():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    holding = SimpleNamespace(
        id=uuid.uuid4(),
        ticker="005930",
        transactions=[_tx(TransactionType.BUY, "10", date(2024, 1, 2))],
    )

    with patch(
        "app.services.snapshot_service.stock_fetcher.get_price_history",
        return_value=[_bar(date(2024, 1, 2), "100"), _bar(date(2024, 1, 3), "110")],
    ):
        await rebuild_holding_snapshots(
            db,
            holding,
            start=date(2024, 1, 2),
            invalidate_start=date(2024, 1, 4),
            end=date(2024, 1, 3),
        )

    statement = db.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    # Must clear from the earliest re-inserted date (start), not the later
    # invalidate_start, otherwise re-inserting 01-02/01-03 duplicates rows.
    assert "daily_snapshots.snapshot_date >= '2024-01-02'" in compiled


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


# ---------------------------------------------------------------------------
# Task 3: finalize_market_snapshots tests
# ---------------------------------------------------------------------------

KST = ZoneInfo("Asia/Seoul")


def _holding_ns(ticker, *txs, first_buy=date(2026, 1, 2)):
    from types import SimpleNamespace
    return SimpleNamespace(id=uuid.uuid4(), ticker=ticker, market=Market.KRX,
                           first_buy_date=first_buy, transactions=list(txs))


def _pr(ticker, price, price_date, market=Market.KRX):
    return PriceResult(ticker=ticker, market=market, name=ticker,
                       currency=Currency.KRW if market == Market.KRX else Currency.USD,
                       price=Decimal(price), price_date=price_date)


async def _captured_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_finalize_skips_intraday_and_writes_confirmed(monkeypatch):
    holding = _holding_ns("005930", _tx(TransactionType.BUY, "2", date(2026, 1, 2)))
    now = datetime(2026, 6, 22, 10, 8, tzinfo=KST)  # 장중
    captured = []

    async def fake_upsert(db, holding_id, snapshot_date, close_price, total_value):
        captured.append((snapshot_date, close_price, total_value))

    monkeypatch.setattr(snapshot_service, "_upsert_snapshot", fake_upsert)
    db = await _captured_db()
    results = await snapshot_service.finalize_market_snapshots(
        db, [holding], now,
        get_price=lambda t: _pr(t, "2885000", date(2026, 6, 22)),
    )
    # 장중 → skip, upsert 없음
    assert captured == []
    assert results["skipped_intraday"] == ["005930"]


@pytest.mark.asyncio
async def test_finalize_writes_at_price_date_with_ledger_quantity(monkeypatch):
    holding = _holding_ns("005930", _tx(TransactionType.BUY, "2", date(2026, 1, 2)))
    now = datetime(2026, 6, 22, 15, 45, tzinfo=KST)  # 마감 후
    captured = []

    async def fake_upsert(db, holding_id, snapshot_date, close_price, total_value):
        captured.append((snapshot_date, close_price, total_value))

    monkeypatch.setattr(snapshot_service, "_upsert_snapshot", fake_upsert)
    db = await _captured_db()
    await snapshot_service.finalize_market_snapshots(
        db, [holding], now,
        get_price=lambda t: _pr(t, "2900000", date(2026, 6, 22)),
    )
    assert captured == [(date(2026, 6, 22), Decimal("2900000"), Decimal("5800000"))]


@pytest.mark.asyncio
async def test_finalize_isolates_ticker_failure(monkeypatch):
    h1 = _holding_ns("005930", _tx(TransactionType.BUY, "1", date(2026, 1, 2)))
    h2 = _holding_ns("000660", _tx(TransactionType.BUY, "1", date(2026, 1, 2)))
    now = datetime(2026, 6, 22, 15, 45, tzinfo=KST)
    written = []

    async def fake_upsert(db, holding_id, snapshot_date, close_price, total_value):
        written.append(close_price)

    def flaky(ticker):
        if ticker == "005930":
            raise RuntimeError("boom")
        return _pr(ticker, "100", date(2026, 6, 22))

    monkeypatch.setattr(snapshot_service, "_upsert_snapshot", fake_upsert)
    db = await _captured_db()
    results = await snapshot_service.finalize_market_snapshots(db, [h1, h2], now, get_price=flaky)
    assert written == [Decimal("100")]
    assert results["failed"] == ["005930"]


def test_quantity_on_date_uses_ledger():
    holding = _holding_ns(
        "005930",
        _tx(TransactionType.BUY, "10", date(2026, 1, 2)),
        _tx(TransactionType.SELL, "4", date(2026, 1, 5)),
    )
    assert snapshot_service._quantity_on_date(holding, date(2026, 1, 4)) == Decimal("10")
    assert snapshot_service._quantity_on_date(holding, date(2026, 1, 5)) == Decimal("6")
