# 시장별 종가·스냅샷 정합성 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 제공자 거래일(`price_date`)만 저장하고, 세션이 끝난 시장만 멱등 upsert로 확정하며, KRX/US를 분리 실행하고 종가를 DB→Redis 동일 값으로 반영해 상단·차트·전일대비를 정확하게 만든다.

**Architecture:** 신규 순수 모듈 `market_session`(마감 판정·쓰기 게이트) + `snapshot_service.finalize_market_snapshots`(게이트+PG `ON CONFLICT` 멱등 upsert+원장 수량) + `price_cache.set_price`(DB→Redis) + 분리 cron + 종목별 비교일 복구 + `updated_at` + dry-run 복구 CLI.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostgreSQL(`sqlalchemy.dialects.postgresql.insert`), APScheduler 3.11.2(인프로세스), Redis, pykrx/yfinance, `zoneinfo`. 테스트: pytest / jest.

**합의 스펙:** `docs/superpowers/reviews/2026-06-22-market-snapshot-merged-spec.md`

**구현 순서:** market_session → set_price → finalize → config → scheduler → updated_at 마이그레이션 → portfolio 비교일 → 복구 CLI → frontend. 앞 순수 모듈이 뒷 작업의 입력이라 의존성 순.

---

## File Structure

- `backend/app/services/market_session.py` (신규) — 순수 함수: 시장 마감 판정/쓰기 게이트.
- `backend/app/services/price_cache.py` (수정) — `set_price`.
- `backend/app/services/snapshot_service.py` (수정) — `finalize_market_snapshots`, `_quantity_on_date`, `_upsert_snapshot`.
- `backend/app/config.py` (수정) — KRX/US cron 설정 + `market_close_overrides`.
- `backend/app/tasks/scheduler.py` (수정) — 분리 cron, finalize 사용, 시작 catch-up.
- `backend/app/models/snapshot.py` (수정) + Alembic 신규 — `updated_at`.
- `backend/app/routers/portfolio.py` (수정) — 종목별 비교일 복구.
- `scripts/reconcile_daily_snapshots.py` (신규) — dry-run/apply 복구.
- `frontend/components/dashboard/DashboardOverview.tsx` (수정) — 장중 라벨/시장 내 날짜 경고.
- 테스트: `backend/tests/test_market_session.py`(신규), `test_scheduler.py`(신규), `test_snapshot_service.py`(수정), `test_price_cache.py`(신규/수정), `test_dashboard_aggregate.py`(수정), `test_reconcile_snapshots.py`(신규), 프론트 `DashboardOverview.test.tsx`(수정).

---

## Task 1: market_session 순수 모듈

**Files:**
- Create: `backend/app/services/market_session.py`
- Test: `backend/tests/test_market_session.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_market_session.py`:
```python
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.models.holding import Market
from app.services.market_session import is_write_confirmed, safe_query_end

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


def _kst(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=KST)


def test_krx_intraday_before_1545_not_confirmed():
    now = _kst(2026, 6, 22, 10, 8)
    assert is_write_confirmed(Market.KRX, date(2026, 6, 22), now) is False


def test_krx_confirmed_after_1545():
    now = _kst(2026, 6, 22, 15, 45)
    assert is_write_confirmed(Market.KRX, date(2026, 6, 22), now) is True


def test_past_session_always_confirmed():
    now = _kst(2026, 6, 22, 10, 0)
    assert is_write_confirmed(Market.KRX, date(2026, 6, 19), now) is True


def test_us_prior_session_confirmed_at_kst_morning():
    # KST 화 06:30 → US 월요일 세션은 마감(ET 16:00 월 = KST 05~06 화)
    now = _kst(2026, 6, 23, 6, 30)
    # provider price_date(미 직전 거래일)는 US 타임존 오늘보다 과거 → 확정
    assert is_write_confirmed(Market.US, date(2026, 6, 22), now) is True


def test_krx_override_blocks_until_1630():
    overrides = {date(2026, 11, 12): time(16, 30)}
    early = _kst(2026, 11, 12, 16, 29)
    late = _kst(2026, 11, 12, 16, 30)
    assert is_write_confirmed(Market.KRX, date(2026, 11, 12), early, close_overrides=overrides) is False
    assert is_write_confirmed(Market.KRX, date(2026, 11, 12), late, close_overrides=overrides) is True


def test_safe_query_end_excludes_today_before_close():
    now = _kst(2026, 6, 22, 10, 8)
    assert safe_query_end(Market.KRX, now) == date(2026, 6, 21)


def test_safe_query_end_includes_today_after_close():
    now = _kst(2026, 6, 22, 15, 45)
    assert safe_query_end(Market.KRX, now) == date(2026, 6, 22)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_market_session.py -q`
Expected: FAIL (`No module named 'app.services.market_session'`)

- [ ] **Step 3: 구현**

Create `backend/app/services/market_session.py`:
```python
"""Market session policy: when a provider price_date may be persisted as a
confirmed close. Pure functions; no DB, no network. zoneinfo only."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.holding import Market

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")

_MARKET_TZ: dict[Market, ZoneInfo] = {Market.KRX: KST, Market.US: ET}
# KRX 정규장 15:30 마감 + 데이터 정착 버퍼 → 15:45. US 16:00 ET.
_DEFAULT_CLOSE: dict[Market, time] = {Market.KRX: time(15, 45), Market.US: time(16, 0)}


def _close_time(market: Market, on: date, close_overrides: dict[date, time] | None) -> time:
    if market == Market.KRX and close_overrides and on in close_overrides:
        return close_overrides[on]
    return _DEFAULT_CLOSE[market]


def is_write_confirmed(
    market: Market,
    price_date: date,
    now: datetime,
    *,
    close_overrides: dict[date, time] | None = None,
) -> bool:
    """True if `price_date` is a completed session for `market` as of `now`."""
    local = now.astimezone(_MARKET_TZ[market])
    market_today = local.date()
    if price_date < market_today:
        return True
    if price_date == market_today:
        return local.time() >= _close_time(market, price_date, close_overrides)
    return False


def safe_query_end(
    market: Market,
    now: datetime,
    *,
    close_overrides: dict[date, time] | None = None,
) -> date:
    """Calendar upper bound for backfill: today only if its session is confirmed."""
    local = now.astimezone(_MARKET_TZ[market])
    market_today = local.date()
    if local.time() >= _close_time(market, market_today, close_overrides):
        return market_today
    return market_today - timedelta(days=1)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_market_session.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: 커밋**

```bash
cd /Users/Shared/workspace/stockfolio
git add backend/app/services/market_session.py backend/tests/test_market_session.py
git commit -m "feat: market_session 마감 판정·쓰기 게이트 순수 모듈"
```

---

## Task 2: price_cache.set_price

**Files:**
- Modify: `backend/app/services/price_cache.py`
- Test: `backend/tests/test_price_cache.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_price_cache.py`:
```python
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.holding import Currency, Market
from app.services import price_cache
from app.services.stock_fetcher import PriceResult


async def test_set_price_writes_serialized_quote_with_ttl(monkeypatch):
    redis = MagicMock()
    redis.setex = AsyncMock()
    monkeypatch.setattr(price_cache, "get_redis", lambda: redis)
    result = PriceResult(
        ticker="005930", market=Market.KRX, name="삼성전자",
        currency=Currency.KRW, price=Decimal("353500"), price_date=date(2026, 6, 22),
    )

    await price_cache.set_price("005930", result)

    redis.setex.assert_awaited_once()
    args = redis.setex.await_args.args
    assert args[0] == "price:005930"
    assert args[1] == price_cache.settings.price_cache_ttl
    assert "353500" in args[2] and "2026-06-22" in args[2]
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_price_cache.py -q`
Expected: FAIL (`module 'app.services.price_cache' has no attribute 'set_price'`)

- [ ] **Step 3: 구현**

In `backend/app/services/price_cache.py`, add after `get_price`:
```python
async def set_price(ticker: str, result: PriceResult) -> None:
    """Overwrite the cached current price (e.g. from a confirmed close job)."""
    r = get_redis()
    await r.setex(_cache_key(ticker), settings.price_cache_ttl, _serialize(result))
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_price_cache.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/app/services/price_cache.py backend/tests/test_price_cache.py
git commit -m "feat: price_cache.set_price 추가(종가 확정 시 Redis 갱신)"
```

---

## Task 3: snapshot_service.finalize_market_snapshots

**Files:**
- Modify: `backend/app/services/snapshot_service.py`
- Test: `backend/tests/test_snapshot_service.py`

- [ ] **Step 1: 실패 테스트 작성**

Append to `backend/tests/test_snapshot_service.py` (파일 상단에 `from datetime import time, timezone`, `from zoneinfo import ZoneInfo`, `from app.models.holding import Currency, Market`, `from app.services.stock_fetcher import PriceResult`, `from app.services import snapshot_service`가 없으면 추가):
```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_snapshot_service.py -q -k "finalize or quantity_on_date"`
Expected: FAIL (`finalize_market_snapshots`/`_quantity_on_date` 없음)

- [ ] **Step 3: 구현**

In `backend/app/services/snapshot_service.py`, add imports at top:
```python
import logging
from datetime import datetime, time
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models.holding import Market
from app.services import stock_fetcher
from app.services.market_session import is_write_confirmed

logger = logging.getLogger(__name__)
```
Append functions:
```python
def _quantity_on_date(holding, on: date) -> Decimal:
    quantity = Decimal(0)
    for transaction in sorted(holding.transactions, key=_transaction_sort_key):
        if transaction.transaction_date > on:
            break
        if transaction.type == TransactionType.BUY:
            quantity += transaction.quantity
        elif transaction.type == TransactionType.SELL:
            quantity -= transaction.quantity
    return quantity


async def _upsert_snapshot(db, holding_id, snapshot_date: date, close_price: Decimal, total_value: Decimal) -> None:
    stmt = pg_insert(DailySnapshot).values(
        holding_id=holding_id, snapshot_date=snapshot_date,
        close_price=close_price, total_value=total_value,
    ).on_conflict_do_update(
        index_elements=["holding_id", "snapshot_date"],
        set_={"close_price": close_price, "total_value": total_value, "updated_at": func.now()},
    )
    await db.execute(stmt)


async def finalize_market_snapshots(
    db,
    holdings,
    now: datetime,
    *,
    get_price=stock_fetcher.get_current_price,
    close_overrides: dict[date, time] | None = None,
) -> dict[str, list]:
    """Confirm today's close for already-closed sessions; idempotent upsert at price_date.
    Returns confirmed (holding, PriceResult) pairs in results['confirmed'] so the caller
    can mirror them to Redis after commit."""
    results: dict[str, list] = {"written": [], "skipped_intraday": [], "failed": [], "confirmed": []}
    for holding in holdings:
        try:
            pr = await asyncio.to_thread(get_price, holding.ticker)
        except Exception as exc:
            logger.warning("finalize price fetch failed ticker=%s: %r", holding.ticker, exc)
            results["failed"].append(holding.ticker)
            continue
        if pr.price is None or not pr.price.is_finite() or pr.price <= 0:
            logger.warning("finalize got unusable price ticker=%s", holding.ticker)
            results["failed"].append(holding.ticker)
            continue
        if not is_write_confirmed(pr.market, pr.price_date, now, close_overrides=close_overrides):
            results["skipped_intraday"].append(holding.ticker)
            continue
        quantity = _quantity_on_date(holding, pr.price_date)
        await _upsert_snapshot(db, holding.id, pr.price_date, pr.price, quantity * pr.price)
        results["written"].append((holding.ticker, pr.price_date))
        results["confirmed"].append((holding, pr))
    return results
```
`func`는 이미 `from sqlalchemy import ... func`로 import돼 있는지 확인하고 없으면 `from sqlalchemy import func` 추가.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_snapshot_service.py -q`
Expected: PASS (기존 + 신규)

- [ ] **Step 5: 커밋**

```bash
git add backend/app/services/snapshot_service.py backend/tests/test_snapshot_service.py
git commit -m "feat: finalize_market_snapshots(게이트+ON CONFLICT 멱등+원장 수량)"
```

---

## Task 4: config — KRX/US cron + market_close_overrides

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: 구현 (설정 추가; 동작은 Task5/Task3에서 검증)**

In `backend/app/config.py` Settings, replace the Scheduler block:
```python
    # Scheduler (KST). KRX finalize after close+buffer; US finalize next KST morning.
    krx_snapshot_hour: int = 15
    krx_snapshot_minute: int = 45
    us_snapshot_hour: int = 6
    us_snapshot_minute: int = 30
    snapshot_misfire_grace_seconds: int = 3600
    # KRX 특별 지연폐장(연 1회 수준): "YYYY-MM-DD=HH:MM" 콤마구분. 예 "2026-11-12=16:30"
    market_close_overrides_raw: str = ""
```
Add a helper after the class (parsing override string into `dict[date, time]`):
```python
def parse_market_close_overrides(raw: str) -> dict:
    from datetime import date as _date, time as _time
    out: dict = {}
    for item in (part.strip() for part in raw.split(",") if part.strip()):
        day_str, _, hm = item.partition("=")
        y, m, d = (int(x) for x in day_str.split("-"))
        hh, mm = (int(x) for x in hm.split(":"))
        out[_date(y, m, d)] = _time(hh, mm)
    return out
```

- [ ] **Step 2: 빠른 검증**

Run: `cd backend && .venv/bin/python -c "from app.config import parse_market_close_overrides as p; from datetime import date,time; assert p('2026-11-12=16:30')=={date(2026,11,12):time(16,30)}; assert p('')=={}; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add backend/app/config.py
git commit -m "feat: KRX/US 분리 스냅샷 스케줄 설정 + 지연폐장 override"
```

---

## Task 5: scheduler — 분리 cron + finalize + 시작 catch-up

**Files:**
- Modify: `backend/app/tasks/scheduler.py`
- Test: `backend/tests/test_scheduler.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_scheduler.py`:
```python
from unittest.mock import MagicMock, patch
from app.tasks import scheduler as sch


def test_start_scheduler_registers_split_jobs_with_hardening():
    fake = MagicMock()
    with patch.object(sch, "scheduler", fake):
        sch.start_scheduler()
    jobs = {c.kwargs.get("id"): c for c in fake.add_job.call_args_list}
    assert {"krx_snapshot", "us_snapshot", "snapshot_backfill"} <= set(jobs)
    for jid in ("krx_snapshot", "us_snapshot"):
        kw = jobs[jid].kwargs
        assert kw["coalesce"] is True
        assert kw["max_instances"] == 1
        assert kw["misfire_grace_time"] == sch.settings.snapshot_misfire_grace_seconds
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_scheduler.py -q`
Expected: FAIL (single `daily_snapshot` job / 옵션 없음)

- [ ] **Step 3: 구현**

Rewrite `backend/app/tasks/scheduler.py`:
```python
"""APScheduler tasks (in-process). KRX finalize at KST 15:45 (mon-fri),
US finalize at KST 06:30 (tue-sat). Startup catch-up backfills past sessions
and finalizes any already-closed market."""
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings, parse_market_close_overrides
from app.database import AsyncSessionLocal
from app.models.holding import Holding, Market
from app.services.market_session import safe_query_end
from app.services.price_cache import set_price
from app.services.snapshot_service import backfill_holding_snapshots, finalize_market_snapshots

settings = get_settings()
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
logger = logging.getLogger(__name__)


def _close_overrides():
    return parse_market_close_overrides(settings.market_close_overrides_raw)


async def _active_holdings(db, market: Market):
    result = await db.execute(
        select(Holding).where(Holding.is_active == True)
        .options(selectinload(Holding.transactions))
    )
    return [h for h in result.scalars().all() if h.market == market]


async def _finalize(market: Market) -> None:
    now = datetime.now(tz=timezone.utc)
    overrides = _close_overrides()
    async with AsyncSessionLocal() as db:
        holdings = await _active_holdings(db, market)
        results = await finalize_market_snapshots(db, holdings, now, close_overrides=overrides)
        await db.commit()
        for holding, pr in results["confirmed"]:
            try:
                await set_price(holding.ticker, pr)
            except Exception:
                logger.warning("finalize redis set failed ticker=%s", holding.ticker, exc_info=True)
    if results["failed"]:
        logger.warning("%s finalize failed tickers=%s", market.value, results["failed"])


async def finalize_krx() -> None:
    await _finalize(Market.KRX)


async def finalize_us() -> None:
    await _finalize(Market.US)


async def _startup_catchup() -> None:
    now = datetime.now(tz=timezone.utc)
    overrides = _close_overrides()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Holding).where(Holding.is_active == True)
            .options(selectinload(Holding.transactions))
        )
        holdings = list(result.scalars().all())
        for holding in holdings:
            try:
                end = safe_query_end(holding.market, now, close_overrides=overrides)
                added = await backfill_holding_snapshots(db, holding, end=end)
                if added:
                    logger.info("Backfilled %s snapshots for holding_id=%s", added, holding.id)
            except Exception:
                logger.exception("Failed to backfill snapshots for holding_id=%s", holding.id)
        await db.commit()
    for market in (Market.KRX, Market.US):
        await _finalize(market)


def start_scheduler() -> None:
    scheduler.add_job(_startup_catchup, trigger="date", id="snapshot_backfill", replace_existing=True)
    scheduler.add_job(
        finalize_krx,
        trigger=CronTrigger(hour=settings.krx_snapshot_hour, minute=settings.krx_snapshot_minute,
                            day_of_week="mon-fri", timezone="Asia/Seoul"),
        id="krx_snapshot", replace_existing=True,
        misfire_grace_time=settings.snapshot_misfire_grace_seconds, coalesce=True, max_instances=1,
    )
    scheduler.add_job(
        finalize_us,
        trigger=CronTrigger(hour=settings.us_snapshot_hour, minute=settings.us_snapshot_minute,
                            day_of_week="tue-sat", timezone="Asia/Seoul"),
        id="us_snapshot", replace_existing=True,
        misfire_grace_time=settings.snapshot_misfire_grace_seconds, coalesce=True, max_instances=1,
    )
    scheduler.start()
```
참고: `finalize_market_snapshots`/`safe_query_end`가 `market`별 holding과 `now`를 받으므로 시작 catch-up은 `safe_query_end`로 `end`를 클램프해 장중 오늘 제외.

- [ ] **Step 4: 통과 확인 + 전체 백엔드**

Run: `cd backend && .venv/bin/python -m pytest tests/test_scheduler.py tests/test_snapshot_service.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/app/tasks/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat: KRX/US 분리 cron + finalize + 시작 catch-up + 미스파이어 하드닝"
```

---

## Task 6: snapshot.updated_at + Alembic

**Files:**
- Modify: `backend/app/models/snapshot.py`
- Create: `backend/alembic/versions/<auto>_daily_snapshot_updated_at.py`

- [ ] **Step 1: 모델 수정**

In `backend/app/models/snapshot.py`, add after `created_at`:
```python
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: 마이그레이션 생성**

Run: `cd backend && .venv/bin/alembic revision --autogenerate -m "daily_snapshot updated_at"`
열어서 `op.add_column('daily_snapshots', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))`인지 확인(없으면 손수 작성). 외부 호출 없음.

- [ ] **Step 3: 적용 + 검증**

Run: `cd backend && .venv/bin/alembic upgrade head && .venv/bin/python -m pytest tests/test_snapshot_service.py -q`
Expected: PASS (upsert가 updated_at 갱신)

- [ ] **Step 4: 커밋**

```bash
git add backend/app/models/snapshot.py backend/alembic/versions/
git commit -m "feat: daily_snapshots.updated_at(감사·관측)"
```

---

## Task 7: portfolio — 종목별 비교일 복구

**Files:**
- Modify: `backend/app/routers/portfolio.py:1524-1542`
- Test: `backend/tests/test_dashboard_aggregate.py`

- [ ] **Step 1: 실패 테스트 작성**

Append to `backend/tests/test_dashboard_aggregate.py` a test that asserts per-holding recovery: build a dashboard via `build_portfolio_dashboard_response`은 DB가 필요하므로, 대신 순수 경로를 검증한다 — 복구 호출이 종목별 `quote.price_date`를 쓰는지 단언하는 단위 테스트를 작성. (기존 `build_dashboard_response` 단위 테스트 패턴 사용; 복구는 `build_portfolio_dashboard_response`에 있으므로 해당 함수의 복구 분기를 별도 헬퍼로 추출해 테스트.)

복구 분기를 헬퍼로 추출:
```python
def _holdings_needing_comparison_recovery(active_holdings, price_quotes):
    needing = []
    for holding in active_holdings:
        quote = price_quotes.get(holding.ticker)
        if quote is None or quote.price_date is None:
            continue
        expected = _previous_weekday(quote.price_date)
        prior = [s.snapshot_date for s in holding.snapshots if s.snapshot_date < quote.price_date]
        if prior and max(prior) >= expected:
            continue
        needing.append((holding, quote.price_date))
    return needing
```
Test:
```python
def test_comparison_recovery_uses_per_holding_price_date():
    from types import SimpleNamespace
    from app.routers.portfolio import _holdings_needing_comparison_recovery, CurrentPriceQuote
    krx = SimpleNamespace(ticker="005930", snapshots=[SimpleNamespace(snapshot_date=date(2026, 6, 19))])
    us = SimpleNamespace(ticker="AAPL", snapshots=[SimpleNamespace(snapshot_date=date(2026, 6, 17))])
    quotes = {
        "005930": CurrentPriceQuote(price=Decimal("1"), price_date=date(2026, 6, 22)),
        "AAPL": CurrentPriceQuote(price=Decimal("1"), price_date=date(2026, 6, 18)),
    }
    needing = _holdings_needing_comparison_recovery([krx, us], quotes)
    # KRX는 6/19 스냅샷 있고 직전영업일(6/19)≥기준 → 복구 불필요. US는 6/17만 있어 6/18 직전(6/17)≥기준 → 불필요.
    assert needing == []
    # KRX 스냅샷을 6/17로 낮추면 6/22 기준 직전영업일(6/19) 미달 → 복구 필요(기준일=6/22)
    krx.snapshots = [SimpleNamespace(snapshot_date=date(2026, 6, 17))]
    needing2 = _holdings_needing_comparison_recovery([krx, us], quotes)
    assert (krx, date(2026, 6, 22)) in needing2
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py -q -k comparison_recovery`
Expected: FAIL (`_holdings_needing_comparison_recovery` 없음)

- [ ] **Step 3: 구현**

In `backend/app/routers/portfolio.py`, extract the helper above (module-level) and rewrite the recovery loop in `build_portfolio_dashboard_response` (현재 1524-1542)를:
```python
    if active_holdings:
        for holding, holding_price_date in _holdings_needing_comparison_recovery(active_holdings, price_quotes):
            try:
                recovered_snapshot_count += await backfill_recent_comparison_snapshots(
                    db, holding, current_price_date=holding_price_date,
                )
            except Exception as exc:
                logger.warning("recent comparison snapshot recovery failed for ticker=%s: %r", holding.ticker, exc)
                warnings.append(f"{holding.ticker} 직전 거래일 스냅샷 복구 실패")
```
전역 `current_price_as_of`/`expected_calendar_date` 기반 분기는 제거(헤더용 `current_price_as_of`/`price_dates_by_market` 계산은 유지).

- [ ] **Step 4: 통과 + 전체 회귀**

Run: `cd backend && .venv/bin/python -m pytest tests/ -q`
Expected: PASS (회귀 포함)

- [ ] **Step 5: 커밋**

```bash
git add backend/app/routers/portfolio.py backend/tests/test_dashboard_aggregate.py
git commit -m "fix: 비교 스냅샷 복구를 종목별 price_date 기준으로"
```

---

## Task 8: 복구 CLI (dry-run/apply)

**Files:**
- Create: `scripts/reconcile_daily_snapshots.py`
- Test: `backend/tests/test_reconcile_snapshots.py` (신규, 순수 로직만)

- [ ] **Step 1: 실패 테스트 작성**

순수 분류 함수 `classify_snapshot_rows(existing_dates, provider_bar_dates)`를 테스트:
```python
from datetime import date
from scripts.reconcile_daily_snapshots import classify_snapshot_rows


def test_classify_detects_holiday_and_missing():
    existing = {date(2026, 6, 19), date(2026, 6, 22)}     # 6/19 US 휴장(잘못된 행)
    provider = {date(2026, 6, 18), date(2026, 6, 22)}     # 실제 거래일
    plan = classify_snapshot_rows(existing, provider)
    assert plan["delete"] == [date(2026, 6, 19)]          # 제공자에 없음 → 삭제
    assert plan["add"] == [date(2026, 6, 18)]             # 누락 → 추가
    assert plan["keep"] == [date(2026, 6, 22)]
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/Shared/workspace/stockfolio && backend/.venv/bin/python -m pytest backend/tests/test_reconcile_snapshots.py -q`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

Create `scripts/reconcile_daily_snapshots.py` with the pure classifier + an async `main(--dry-run/--apply, --since)` that, per active holding, fetches provider bars(`stock_fetcher.get_price_history`) for the window, classifies vs existing snapshots, and on apply uses `rebuild_holding_snapshots`(원장 기반) for add/update and deletes provider-absent derived rows. 최초 전체기간(`first_buy_date`~`safe_query_end`), 자동 보정용은 별 함수로 최근 14일.
```python
def classify_snapshot_rows(existing_dates, provider_bar_dates):
    existing = set(existing_dates); provider = set(provider_bar_dates)
    return {
        "delete": sorted(existing - provider),
        "add": sorted(provider - existing),
        "keep": sorted(existing & provider),
    }
```
(`main`은 DB·네트워크를 쓰며 dry-run이 기본. 인쇄만, `--apply`에서만 변경. 단위 테스트는 `classify_snapshot_rows`만 대상.)

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/Shared/workspace/stockfolio && backend/.venv/bin/python -m pytest backend/tests/test_reconcile_snapshots.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/reconcile_daily_snapshots.py backend/tests/test_reconcile_snapshots.py
git commit -m "feat: daily_snapshots 정합 복구 CLI(dry-run 기본)"
```

---

## Task 9: 프론트 — 장중 라벨 / 시장 내 날짜 경고

**Files:**
- Modify: `frontend/components/dashboard/DashboardOverview.tsx`
- Test: `frontend/__tests__/dashboard/DashboardOverview.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

기존 per-market 헤더 테스트 옆에, 같은 시장 종목 날짜가 다를 때 경고가 뜨는지 테스트. (백엔드가 `warnings`에 "일부 종목 지연"을 넣는 구조를 이미 사용하므로, 프론트는 `dashboard.warnings`를 렌더하는지 + 시장 내 날짜가 모두 같으면 단일 표시인지 검증.)
```tsx
it('keeps a single market date when all holdings share it', () => {
  render(<DashboardOverview dashboard={dashboard} displayCurrency="KRW" onDisplayCurrencyChange={jest.fn()} onRefresh={jest.fn()} isRefreshing={false} lastUpdated={new Date('2026-06-22T09:00:00Z')} />)
  // price_dates_by_market = { KRX: '2026-06-22', US: '2026-06-18' } (fixture)
  expect(screen.getByText(/현재가 기준: 한국 2026-06-22 · 미국 2026-06-18/)).toBeInTheDocument()
})
```
(이미 통과하는 기존 동작 확인 + 장중 라벨은 백엔드 신호가 필요하므로, 신호 필드가 없으면 이 태스크는 "경고 렌더 + 단일/복수 표시"로 한정하고, 장중 라벨은 별 신호 도입 시 후속. 기존 `현재가 기준` 표시는 유지.)

- [ ] **Step 2~4: 구현·검증**

`DashboardOverview`가 `dashboard.warnings`를 이미 렌더하는지 확인하고(현재 렌더함), 시장 내 날짜 표시는 `formatMarketDates`로 이미 충족됨을 회귀 테스트로 고정. 장중 "확정 전" 라벨은 백엔드가 장중 여부 신호를 추가할 때 연결(이번 범위에선 회귀 테스트만).

Run: `cd frontend && npm test -- --runInBand DashboardOverview && npm run build`
Expected: PASS / Compiled

- [ ] **Step 5: 커밋**

```bash
git add frontend/components/dashboard/DashboardOverview.tsx frontend/__tests__/dashboard/DashboardOverview.test.tsx
git commit -m "test: 시장별 기준일 표시 회귀 + 경고 렌더 고정"
```

---

## 최종 검증·배포

- [ ] backend 전체: `cd backend && .venv/bin/python -m pytest tests/ -q`
- [ ] frontend 전체 + 빌드: `cd frontend && npm test -- --runInBand && npm run build`
- [ ] `git diff --check`
- [ ] 복구 CLI dry-run(전체기간) 검토 → DB 백업 → `./svc.sh deploy`(alembic updated_at 포함) → 복구 CLI `--apply` → 재실행 0건
- [ ] 마감 후 검증: 상단=차트 일치, 미 6/19 행 부재·올바른 거래일 저장, 스케줄러 로그 misfire 없음·부분 실패 티커 경고

---

## Self-Review 메모

- 스펙 P0~P2 매핑: P0(저장=price_date T3, 게이트 T1, KRX/US 분리 T5, ON CONFLICT T3, DB→Redis T2·T5, 비교일 종목별 T7, override T1·T4), P1(하드닝·catch-up T5, fetch 분리/로그 T3·T5, 복구 CLI T8, updated_at T6, total_value 원장 T3), P2(시장 내 날짜 경고 T9, 환율 회귀는 기존 통과 + T9, 장중 라벨은 후속 신호 필요로 명시).
- 시그니처 일관성: `is_write_confirmed`/`safe_query_end`(market_session) ↔ `finalize_market_snapshots(close_overrides=)` ↔ `_upsert_snapshot`/`_quantity_on_date` ↔ scheduler `_finalize` ↔ `parse_market_close_overrides`가 전 태스크에서 동일 명칭·인자.
- 불확실성(스펙 §12)으로 남긴 항목: pykrx 장중 반환 실측, 전체기간 복구 비용, 프론트 마지막 history 점 환율/수량 경로, KRX override 운영 프로세스 → 구현 중 확인.
- 장중 "확정 전" 라벨(P2-13)은 백엔드의 "장중 여부" 신호 필드가 선행되어야 하므로, 이번 계획은 회귀 고정까지만 하고 신호 도입을 후속 태스크로 명시(과설계 회피).
