# 대시보드 그룹, 통화, 거래내역 개선 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드에서 전체/그룹별 수익현황을 같은 지표로 비교하고, 기본 원화 환산/달러 별도 표시, 보유종목 그룹 열, 전체 거래내역 조회/수정, 종목 상세 수익현황을 구현한다.

**Architecture:** 기존 scoped portfolio 계산 로직과 lot accounting을 재사용하되, 화면용 통합 payload를 반환하는 `/api/portfolio/dashboard`를 새로 추가한다. 거래내역은 holdings 하위 endpoint의 delete/classification/replay 규칙을 공용 transaction endpoint로 확장하고, 프론트엔드는 새 aggregate payload 중심의 대시보드 컴포넌트로 재구성한다.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest, yfinance, Next.js 14 App Router, TypeScript, SWR, Jest, TradingView Lightweight Charts, Tailwind.

---

## 파일 구조

### 선행 변경 안정화

- Modify: `backend/app/models/holding.py`
- Modify: `backend/app/schemas/holding.py`
- Modify: `backend/app/services/lot_accounting.py`
- Modify: `backend/app/routers/holdings.py`
- Modify: `backend/app/routers/portfolio.py`
- Modify: `frontend/components/holdings/HoldingForm.tsx`
- Modify: `frontend/components/holdings/AddTransactionForm.tsx`
- Modify: `frontend/components/dashboard/PortfolioSummary.tsx`
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Create: `backend/alembic/versions/0f4c2a1b9d3e_add_transaction_principal_flow.py`
- Create: `scripts/rebuild_mkfrom_portfolio.py`

현재 workspace에는 위 변경이 이미 존재한다. 구현 시작 전 이 선행 변경을 검증하고 별도 커밋으로 안정화한다.

### 백엔드 신규/변경

- Create: `backend/app/services/exchange_rate.py`
- Create: `backend/app/schemas/dashboard.py`
- Create: `backend/app/schemas/transaction.py`
- Create: `backend/app/routers/transactions.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/routers/portfolio.py`
- Modify: `backend/app/routers/holdings.py`
- Modify: `backend/app/schemas/holding.py`
- Modify: `backend/app/services/lot_accounting.py`
- Test: `backend/tests/test_dashboard_aggregate.py`
- Test: `backend/tests/test_transactions_api.py`
- Test: `backend/tests/test_exchange_rate.py`
- Test: `backend/tests/test_holding_detail_performance.py`

### 프론트엔드 신규/변경

- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/page.tsx`
- Create: `frontend/app/transactions/page.tsx`
- Modify: `frontend/components/layout/Navbar.tsx`
- Create: `frontend/components/dashboard/DashboardOverview.tsx`
- Create: `frontend/components/dashboard/DisplayCurrencyToggle.tsx`
- Create: `frontend/components/dashboard/GroupPerformanceTable.tsx`
- Create: `frontend/components/dashboard/DashboardChartControls.tsx`
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Modify: `frontend/components/dashboard/HoldingsTable.tsx`
- Create: `frontend/components/transactions/TransactionsTable.tsx`
- Create: `frontend/components/transactions/TransactionFilters.tsx`
- Create: `frontend/components/transactions/TransactionEditPanel.tsx`
- Create: `frontend/components/holdings/HoldingPerformanceSummary.tsx`
- Create: `frontend/components/holdings/HoldingGroupBreakdown.tsx`
- Modify: `frontend/app/holdings/[id]/page.tsx`
- Modify: `frontend/components/holdings/TransactionList.tsx`
- Test: `frontend/__tests__/dashboard/DashboardOverview.test.tsx`
- Test: `frontend/__tests__/components/GroupPerformanceTable.test.tsx`
- Test: `frontend/__tests__/components/HoldingsTable.test.tsx`
- Test: `frontend/__tests__/transactions/TransactionsPage.test.tsx`
- Test: `frontend/__tests__/holdings/HoldingPage.test.tsx`

---

## Task 0: 선행 투자원금처리 변경 안정화

**Files:**
- Existing modified files listed in "선행 변경 안정화"

- [ ] **Step 1: 현재 선행 변경 검증 명령 실행**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/
cd frontend && npm test
cd frontend && npm run build
git diff --check
```

Expected:

- Backend: `251 passed, 1 skipped` 또는 최신 테스트 수 기준 전체 통과.
- Frontend: 전체 Jest 테스트 통과.
- Build: `npm run build` exit code 0.
- Diff check: 출력 없음.

- [ ] **Step 2: 실패 시 선행 변경만 수정**

수정 범위는 기존 투자원금처리 변경 파일로 제한한다. 새 대시보드/거래내역 기능 파일을 만들지 않는다.

- [ ] **Step 3: 선행 변경 커밋**

Run:

```bash
git add backend/app/models/__init__.py \
  backend/app/models/holding.py \
  backend/app/routers/holdings.py \
  backend/app/routers/portfolio.py \
  backend/app/schemas/holding.py \
  backend/app/schemas/portfolio.py \
  backend/app/services/lot_accounting.py \
  backend/app/services/stock_fetcher.py \
  backend/tests/test_groups_api.py \
  backend/tests/test_holdings_lots_api.py \
  backend/tests/test_scoped_portfolio.py \
  backend/tests/test_stock_fetcher.py \
  frontend/__tests__/components/PortfolioSummary.test.tsx \
  frontend/__tests__/dashboard/PortfolioChart.test.ts \
  frontend/components/dashboard/PortfolioChart.tsx \
  frontend/components/dashboard/PortfolioSummary.tsx \
  frontend/components/holdings/AddTransactionForm.tsx \
  frontend/components/holdings/HoldingForm.tsx \
  frontend/lib/api.ts \
  frontend/lib/types.ts \
  backend/alembic/versions/0f4c2a1b9d3e_add_transaction_principal_flow.py \
  scripts/rebuild_mkfrom_portfolio.py
git commit -m "feat: track transaction principal flows"
```

Expected:

- 선행 변경이 별도 커밋으로 고정된다.

---

## Task 1: 환율 서비스 추가

**Files:**
- Create: `backend/app/services/exchange_rate.py`
- Test: `backend/tests/test_exchange_rate.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_exchange_rate.py`:

```python
from datetime import date
from decimal import Decimal

import pytest

from app.services.exchange_rate import ExchangeRate, convert_money


def test_convert_usd_to_krw_with_current_rate():
    rate = ExchangeRate(base="USD", quote="KRW", rate=Decimal("1380"), as_of=date(2026, 6, 4))

    assert convert_money(Decimal("10"), "USD", "KRW", rate) == Decimal("13800")


def test_convert_krw_to_krw_without_rate():
    assert convert_money(Decimal("1234"), "KRW", "KRW", None) == Decimal("1234")


def test_convert_usd_to_krw_requires_rate():
    with pytest.raises(ValueError, match="USD/KRW exchange rate is required"):
        convert_money(Decimal("10"), "USD", "KRW", None)
```

- [ ] **Step 2: RED 확인**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_exchange_rate.py -q
```

Expected:

- FAIL: `ModuleNotFoundError: No module named 'app.services.exchange_rate'`

- [ ] **Step 3: 최소 구현 작성**

Create `backend/app/services/exchange_rate.py`:

```python
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import yfinance as yf


@dataclass(frozen=True)
class ExchangeRate:
    base: str
    quote: str
    rate: Decimal
    as_of: date


def convert_money(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    rate: ExchangeRate | None,
) -> Decimal:
    if from_currency == to_currency:
        return amount
    if from_currency == "USD" and to_currency == "KRW":
        if rate is None:
            raise ValueError("USD/KRW exchange rate is required")
        return amount * rate.rate
    raise ValueError(f"Unsupported currency conversion: {from_currency} -> {to_currency}")


async def get_usd_krw_rate() -> ExchangeRate:
    ticker = yf.Ticker("USDKRW=X")
    history = ticker.history(period="5d")
    if history.empty:
        raise ValueError("USD/KRW exchange rate is unavailable")
    row = history.dropna().iloc[-1]
    return ExchangeRate(
        base="USD",
        quote="KRW",
        rate=Decimal(str(row["Close"])),
        as_of=history.dropna().index[-1].date(),
    )
```

- [ ] **Step 4: GREEN 확인**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_exchange_rate.py -q
```

Expected:

- `3 passed`

---

## Task 2: 대시보드 aggregate schema와 backend 계산 추가

**Files:**
- Create: `backend/app/schemas/dashboard.py`
- Modify: `backend/app/routers/portfolio.py`
- Test: `backend/tests/test_dashboard_aggregate.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_dashboard_aggregate.py`:

```python
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import uuid

from app.models.holding import Currency, PrincipalFlow
from app.routers.portfolio import _build_dashboard_payload
from app.services.exchange_rate import ExchangeRate

from tests.test_scoped_portfolio import _buy, _holding


def test_dashboard_payload_converts_usd_to_krw_and_includes_group_rows():
    source_a = uuid.uuid4()
    source_b = uuid.uuid4()
    krw_holding_id = uuid.uuid4()
    usd_holding_id = uuid.uuid4()
    krw = _holding(
        _buy(
            krw_holding_id,
            "005930",
            Currency.KRW,
            source_group_id=source_a,
            quantity="10",
            price="1000",
            principal_flow=PrincipalFlow.DEPOSIT,
        )
    )
    usd = _holding(
        _buy(
            usd_holding_id,
            "AAPL",
            Currency.USD,
            source_group_id=source_b,
            quantity="2",
            price="10",
            principal_flow=PrincipalFlow.DEPOSIT,
        )
    )
    groups = [
        SimpleNamespace(kind="source", id=source_a, name="모음통장", color="#111111"),
        SimpleNamespace(kind="source", id=source_b, name="긴급통장", color="#222222"),
    ]
    rate = ExchangeRate(base="USD", quote="KRW", rate=Decimal("1000"), as_of=date(2026, 6, 4))

    payload = _build_dashboard_payload(
        [krw, usd],
        groups,
        current_prices={"005930": Decimal("1200"), "AAPL": Decimal("11")},
        display_currency="KRW",
        exchange_rate=rate,
    )

    assert payload.display_currency == "KRW"
    assert payload.summary.total_invested_principal == Decimal("30000")
    assert payload.summary.total_current_value == Decimal("34000")
    assert [row.name for row in payload.groups] == ["모음통장", "긴급통장"]
    assert payload.groups[0].summary.total_invested_principal == Decimal("10000")
    assert payload.groups[1].summary.total_invested_principal == Decimal("20000")
```

- [ ] **Step 2: RED 확인**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py -q
```

Expected:

- FAIL: `_build_dashboard_payload` import 또는 schema 미정의 실패.

- [ ] **Step 3: schema 작성**

Create `backend/app/schemas/dashboard.py`:

```python
from datetime import date
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import BaseModel

from app.schemas.portfolio import AccountingStatus


DisplayCurrency = Literal["KRW", "USD"]
DashboardGroupKind = Literal["source", "rollup", "unclassified"]


class DashboardExchangeRate(BaseModel):
    base: str
    quote: str
    rate: Decimal
    as_of: date


class DashboardMetricSummary(BaseModel):
    total_invested_principal: Decimal | None
    total_cost_basis: Decimal | None
    total_current_value: Decimal | None
    total_profit_loss: Decimal | None
    total_profit_loss_pct: Decimal | None
    holding_count: int
    accounting_status: AccountingStatus = "ok"
    warnings: list[str] = []


class DashboardGroupSummary(BaseModel):
    kind: DashboardGroupKind
    id: uuid.UUID | None
    name: str
    color: str | None = None
    summary: DashboardMetricSummary


class DashboardHistoryPoint(BaseModel):
    snapshot_date: date
    total_value: Decimal | None
    total_invested_principal: Decimal | None
    total_profit_loss: Decimal | None
    accounting_status: AccountingStatus
    warnings: list[str] = []


class DashboardHistorySeries(BaseModel):
    key: str
    name: str
    kind: DashboardGroupKind | Literal["all"]
    points: list[DashboardHistoryPoint]


class DashboardHoldingGroupBadge(BaseModel):
    source_group_id: uuid.UUID | None
    name: str
    color: str | None = None
    remaining_quantity: Decimal


class DashboardHolding(BaseModel):
    holding_id: uuid.UUID
    ticker: str
    name: str | None
    currency: str
    remaining_quantity: Decimal
    remaining_cost_basis: Decimal
    current_value: Decimal | None
    unrealized_profit_loss: Decimal | None
    groups: list[DashboardHoldingGroupBadge]


class DashboardOut(BaseModel):
    display_currency: DisplayCurrency
    exchange_rate: DashboardExchangeRate | None
    summary: DashboardMetricSummary
    groups: list[DashboardGroupSummary]
    history: list[DashboardHistorySeries]
    holdings: list[DashboardHolding]
    warnings: list[str]
```

- [ ] **Step 4: dashboard builder 최소 구현**

Modify `backend/app/routers/portfolio.py`:

```python
from app.schemas.dashboard import (
    DashboardExchangeRate,
    DashboardGroupSummary,
    DashboardMetricSummary,
    DashboardOut,
)
from app.services.exchange_rate import ExchangeRate, convert_money, get_usd_krw_rate
```

Add helper functions near scoped dashboard helpers:

```python
def _convert_optional(
    value: Decimal | None,
    from_currency: Currency,
    display_currency: str,
    exchange_rate: ExchangeRate | None,
) -> Decimal | None:
    if value is None:
        return None
    return convert_money(value, from_currency.value, display_currency, exchange_rate)


def _merge_summaries(
    summaries: list[tuple[Currency, PortfolioCurrencySummary]],
    display_currency: str,
    exchange_rate: ExchangeRate | None,
) -> DashboardMetricSummary:
    invested = Decimal(0)
    cost_basis = Decimal(0)
    current_value = Decimal(0)
    current_available = True
    holding_count = 0
    for currency, summary in summaries:
        if summary.total_invested_principal is not None:
            invested += _convert_optional(summary.total_invested_principal, currency, display_currency, exchange_rate) or Decimal(0)
        if summary.total_cost_basis is not None:
            cost_basis += _convert_optional(summary.total_cost_basis, currency, display_currency, exchange_rate) or Decimal(0)
        if summary.total_current_value is None:
            current_available = False
        else:
            current_value += _convert_optional(summary.total_current_value, currency, display_currency, exchange_rate) or Decimal(0)
        holding_count += summary.holding_count
    profit_loss = current_value - invested if current_available else None
    return DashboardMetricSummary(
        total_invested_principal=invested,
        total_cost_basis=cost_basis,
        total_current_value=current_value if current_available else None,
        total_profit_loss=profit_loss,
        total_profit_loss_pct=(profit_loss / invested * 100 if profit_loss is not None and invested > 0 else None),
        holding_count=holding_count,
    )
```

Add `_build_dashboard_payload(...)`:

```python
def _build_dashboard_payload(
    holdings: list[Holding],
    groups: list,
    *,
    current_prices: dict[str, Decimal | None],
    display_currency: str,
    exchange_rate: ExchangeRate | None,
) -> DashboardOut:
    all_scope = PortfolioScope("all")
    summary, scoped_holdings = _build_scoped_dashboard_payload(holdings, all_scope, current_prices)
    summary_rows = [
        (currency, currency_summary)
        for currency, currency_summary in summary.currencies.items()
        if display_currency == "KRW" or currency.value == display_currency
    ]
    dashboard_groups = []
    for group in groups:
        scope = PortfolioScope(group.kind, group.id)
        group_summary, _ = _build_scoped_dashboard_payload(holdings, scope, current_prices)
        dashboard_groups.append(
            DashboardGroupSummary(
                kind=group.kind,
                id=group.id,
                name=group.name,
                color=getattr(group, "color", None),
                summary=_merge_summaries(
                    [
                        (currency, currency_summary)
                        for currency, currency_summary in group_summary.currencies.items()
                        if display_currency == "KRW" or currency.value == display_currency
                    ],
                    display_currency,
                    exchange_rate,
                ),
            )
        )
    return DashboardOut(
        display_currency=display_currency,
        exchange_rate=(
            DashboardExchangeRate.model_validate(exchange_rate.__dict__)
            if exchange_rate is not None
            else None
        ),
        summary=_merge_summaries(summary_rows, display_currency, exchange_rate),
        groups=dashboard_groups,
        history=[],
        holdings=[],
        warnings=list(summary.warnings),
    )
```

- [ ] **Step 5: GREEN 확인**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py -q
```

Expected:

- 위 신규 테스트 통과.

---

## Task 3: `/api/portfolio/dashboard` endpoint 완성

**Files:**
- Modify: `backend/app/routers/portfolio.py`
- Test: `backend/tests/test_dashboard_aggregate.py`

- [ ] **Step 1: API 테스트 추가**

Append to `backend/tests/test_dashboard_aggregate.py`:

```python
async def test_dashboard_endpoint_requires_authentication(client):
    response = client.get("/api/portfolio/dashboard")

    assert response.status_code == 401
```

Add authenticated endpoint test following `test_scoped_portfolio.py` fixture style:

```python
def test_dashboard_endpoint_returns_default_krw_payload(client, user, monkeypatch):
    async def fake_dashboard(*_args, **_kwargs):
        from app.schemas.dashboard import DashboardMetricSummary, DashboardOut
        return DashboardOut(
            display_currency="KRW",
            exchange_rate=None,
            summary=DashboardMetricSummary(
                total_invested_principal="0",
                total_cost_basis="0",
                total_current_value="0",
                total_profit_loss="0",
                total_profit_loss_pct=None,
                holding_count=0,
            ),
            groups=[],
            history=[],
            holdings=[],
            warnings=[],
        )

    monkeypatch.setattr("app.routers.portfolio.build_portfolio_dashboard", fake_dashboard)
    response = client.get("/api/portfolio/dashboard")

    assert response.status_code == 200
    assert response.json()["display_currency"] == "KRW"
```

- [ ] **Step 2: RED 확인**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py -q
```

Expected:

- FAIL: route not found 또는 monkeypatch target 없음.

- [ ] **Step 3: endpoint 구현**

Add to `backend/app/routers/portfolio.py`:

```python
async def _load_dashboard_groups(db: AsyncSession, user_id: uuid.UUID) -> list:
    sources = list((await db.execute(select(SourceGroup).where(SourceGroup.user_id == user_id))).scalars().all())
    rollups = list((await db.execute(select(RollupGroup).where(RollupGroup.user_id == user_id))).scalars().all())
    group_rows = [
        type("DashboardGroup", (), {"kind": "source", "id": source.id, "name": source.name, "color": source.color})
        for source in sources
    ]
    group_rows.extend(
        type("DashboardGroup", (), {"kind": "rollup", "id": rollup.id, "name": rollup.name, "color": rollup.color})
        for rollup in rollups
    )
    return group_rows


async def build_portfolio_dashboard(
    db: AsyncSession,
    user_id: uuid.UUID,
    display_currency: str,
) -> DashboardOut:
    holdings = await _load_scoped_holdings(db, user_id, include_inactive=True)
    prices = await _fetch_current_prices(_scoped_price_tickers(holdings, PortfolioScope("all")))
    exchange_rate = await get_usd_krw_rate() if display_currency == "KRW" else None
    groups = await _load_dashboard_groups(db, user_id)
    return _build_dashboard_payload(
        holdings,
        groups,
        current_prices=prices,
        display_currency=display_currency,
        exchange_rate=exchange_rate,
    )


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(
    display_currency: Literal["KRW", "USD"] = "KRW",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await build_portfolio_dashboard(db, current_user.id, display_currency)
```

- [ ] **Step 4: GREEN 확인**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py -q
```

Expected:

- 신규 dashboard endpoint 테스트 통과.

---

## Task 4: dashboard holdings group badges와 history series 채우기

**Files:**
- Modify: `backend/app/routers/portfolio.py`
- Test: `backend/tests/test_dashboard_aggregate.py`

- [ ] **Step 1: holdings group badge 실패 테스트 추가**

Append:

```python
def test_dashboard_holding_group_badges_show_remaining_source_lots():
    source = uuid.uuid4()
    holding_id = uuid.uuid4()
    holding = _holding(
        _buy(holding_id, "005930", Currency.KRW, source_group_id=source, quantity="3", price="1000")
    )
    group = SimpleNamespace(kind="source", id=source, name="모음통장", color="#111111")
    payload = _build_dashboard_payload(
        [holding],
        [group],
        current_prices={"005930": Decimal("1200")},
        display_currency="KRW",
        exchange_rate=None,
    )

    assert payload.holdings[0].groups[0].name == "모음통장"
    assert payload.holdings[0].groups[0].remaining_quantity == Decimal("3")
```

- [ ] **Step 2: RED 확인**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py::test_dashboard_holding_group_badges_show_remaining_source_lots -q
```

Expected:

- FAIL: `payload.holdings` empty.

- [ ] **Step 3: holdings 채우기**

In `_build_dashboard_payload`, add group name lookup and holdings mapping:

```python
source_names = {
    group.id: (group.name, getattr(group, "color", None))
    for group in groups
    if group.kind == "source"
}
dashboard_holdings = []
for row in scoped_holdings.holdings:
    badges = []
    for position in _trusted_scoped_positions(holdings, PortfolioScope("all"), current_prices)[1]:
        if position.ticker != row.ticker or position.currency != row.currency.value:
            continue
        name, color = source_names.get(position.source_group_id, ("미분류", None))
        badges.append(
            DashboardHoldingGroupBadge(
                source_group_id=position.source_group_id,
                name=name,
                color=color,
                remaining_quantity=position.remaining_quantity,
            )
        )
    dashboard_holdings.append(
        DashboardHolding(
            holding_id=row.holding_id,
            ticker=row.ticker,
            name=row.name,
            currency=row.currency.value,
            remaining_quantity=row.remaining_quantity,
            remaining_cost_basis=row.remaining_cost_basis,
            current_value=_convert_optional(row.current_value, row.currency, display_currency, exchange_rate),
            unrealized_profit_loss=_convert_optional(row.unrealized_profit_loss, row.currency, display_currency, exchange_rate),
            groups=badges,
        )
    )
```

Update return `holdings=dashboard_holdings`.

- [ ] **Step 4: history 실패 테스트 추가**

Append:

```python
def test_dashboard_history_includes_all_series_key():
    source = uuid.uuid4()
    holding_id = uuid.uuid4()
    holding = _holding(
        _buy(holding_id, "005930", Currency.KRW, source_group_id=source, quantity="1", price="1000")
    )
    holding.snapshots = [
        SimpleNamespace(snapshot_date=date(2026, 6, 1), close_price=Decimal("1100")),
    ]
    group = SimpleNamespace(kind="source", id=source, name="모음통장", color="#111111")

    payload = _build_dashboard_payload(
        [holding],
        [group],
        current_prices={"005930": Decimal("1200")},
        display_currency="KRW",
        exchange_rate=None,
    )

    assert payload.history[0].key == "all"
    assert payload.history[0].points[0].total_value == Decimal("1100")
```

- [ ] **Step 5: history 구현**

Use `_build_scoped_history(holdings, scope)` for all and groups, then convert points:

```python
def _dashboard_history_series(
    holdings: list[Holding],
    key: str,
    name: str,
    kind: str,
    scope: PortfolioScope,
    display_currency: str,
    exchange_rate: ExchangeRate | None,
) -> DashboardHistorySeries:
    history = _build_scoped_history(holdings, scope)
    points_by_date = {}
    for currency, points in history.series.items():
        if display_currency != "KRW" and currency.value != display_currency:
            continue
        for point in points:
            row = points_by_date.setdefault(
                point.snapshot_date,
                {"value": Decimal(0), "principal": Decimal(0), "warnings": [], "status": "ok"},
            )
            if point.total_value is None or point.total_invested_principal is None:
                row["status"] = "requires_review"
                row["value"] = None
                row["principal"] = None
            elif row["value"] is not None:
                row["value"] += _convert_optional(point.total_value, currency, display_currency, exchange_rate) or Decimal(0)
                row["principal"] += _convert_optional(point.total_invested_principal, currency, display_currency, exchange_rate) or Decimal(0)
            row["warnings"].extend(point.warnings)
    return DashboardHistorySeries(
        key=key,
        name=name,
        kind=kind,
        points=[
            DashboardHistoryPoint(
                snapshot_date=snapshot_date,
                total_value=row["value"],
                total_invested_principal=row["principal"],
                total_profit_loss=(
                    row["value"] - row["principal"]
                    if row["value"] is not None and row["principal"] is not None
                    else None
                ),
                accounting_status=row["status"],
                warnings=row["warnings"],
            )
            for snapshot_date, row in sorted(points_by_date.items())
        ],
    )
```

- [ ] **Step 6: 전체 dashboard aggregate 테스트**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py tests/test_scoped_portfolio.py -q
```

Expected:

- 모두 통과.

---

## Task 5: 거래내역 목록/수정 API

**Files:**
- Create: `backend/app/schemas/transaction.py`
- Create: `backend/app/routers/transactions.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/routers/holdings.py`
- Test: `backend/tests/test_transactions_api.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_transactions_api.py`:

```python
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.models.group import BuyLot
from app.models.holding import Currency, Holding, Market, PrincipalFlow, Transaction, TransactionType
from app.models.user import User
from app.routers.deps import get_current_user
from app.routers.transactions import router


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

    def queue(self, *results):
        self.results.extend(results)

    async def execute(self, _query):
        assert self.results, "unexpected database query"
        return self.results.pop(0)

    async def flush(self):
        return None


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


def _holding_with_buy(user_id, *, ticker="005930", name="삼성전자", quantity=Decimal("2"), price=Decimal("1000")):
    holding = Holding(
        id=uuid.uuid4(),
        user_id=user_id,
        ticker=ticker,
        market=Market.KRX,
        name=name,
        quantity=quantity,
        avg_price=price,
        currency=Currency.KRW,
        first_buy_date=date(2026, 6, 1),
        is_active=True,
        transactions=[],
        buy_lots=[],
    )
    tx = Transaction(
        id=uuid.uuid4(),
        holding_id=holding.id,
        holding=holding,
        user_id=user_id,
        source_group_id=None,
        type=TransactionType.BUY,
        quantity=quantity,
        price=price,
        transaction_date=date(2026, 6, 1),
        principal_flow=PrincipalFlow.DEPOSIT,
        transaction_labels=[],
        sell_allocations=[],
    )
    lot = BuyLot(
        id=uuid.uuid4(),
        transaction_id=tx.id,
        holding_id=holding.id,
        transaction=tx,
        holding=holding,
        user_id=user_id,
        source_group_id=None,
        original_quantity=quantity,
        remaining_quantity=quantity,
        unit_price=price,
    )
    tx.buy_lot = lot
    holding.transactions = [tx]
    holding.buy_lots = [lot]
    return holding


def test_transactions_list_requires_authentication(client):
    response = client.get("/api/transactions")

    assert response.status_code == 401


def test_transactions_list_returns_owned_transactions(client, user, db):
    holding = _holding_with_buy(user.id)
    tx = holding.transactions[0]
    db.queue(_Result(many=[tx]))

    response = client.get("/api/transactions")

    assert response.status_code == 200
    assert response.json()["transactions"][0]["id"] == str(tx.id)
    assert response.json()["transactions"][0]["ticker"] == "005930"


def test_patch_buy_transaction_updates_price_and_replays(client, user, db, monkeypatch):
    holding = _holding_with_buy(user.id, quantity=Decimal("2"), price=Decimal("1000"))
    tx = holding.transactions[0]
    db.queue(_Result(one=tx), _Result(one=holding))

    async def _skip_snapshot_rebuild(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.routers.transactions._rebuild_snapshots_after_mutation", _skip_snapshot_rebuild)

    response = client.patch(
        f"/api/transactions/{tx.id}",
        json={
            "transaction_date": "2026-06-01",
            "quantity": "3",
            "price": "1200",
            "principal_flow": "DEPOSIT",
            "source_group_id": None,
            "label_ids": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["quantity"] == "3"
    assert response.json()["price"] == "1200"
```

- [ ] **Step 2: RED 확인**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_transactions_api.py -q
```

Expected:

- FAIL: route not found.

- [ ] **Step 3: schemas 작성**

Create `backend/app/schemas/transaction.py`:

```python
from datetime import date, datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, Field, model_validator

from app.models.holding import PrincipalFlow, TransactionType


class TransactionListItemOut(BaseModel):
    id: uuid.UUID
    holding_id: uuid.UUID
    ticker: str
    holding_name: str
    type: TransactionType
    transaction_date: date
    quantity: Decimal
    price: Decimal
    amount: Decimal
    principal_flow: PrincipalFlow
    source_group_id: uuid.UUID | None
    source_group_name: str | None
    label_ids: list[uuid.UUID]
    requires_review: bool
    created_at: datetime


class TransactionListOut(BaseModel):
    transactions: list[TransactionListItemOut]


class TransactionUpdateIn(BaseModel):
    transaction_date: date | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    principal_flow: PrincipalFlow | None = None
    source_group_id: uuid.UUID | None = None
    label_ids: list[uuid.UUID] | None = None

    @model_validator(mode="after")
    def validate_labels(self):
        if self.label_ids is not None and len(self.label_ids) != len(set(self.label_ids)):
            raise ValueError("label_ids must not contain duplicates")
        return self
```

- [ ] **Step 4: router 작성**

Create `backend/app/routers/transactions.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.holding import Holding, Transaction, TransactionType
from app.models.user import User
from app.routers.deps import get_current_user
from app.routers.holdings import (
    _get_owned_holding,
    _rebuild_snapshots_after_mutation,
    _recalculate_holding,
    _replace_transaction_labels,
    _replay_and_update_lots,
    _transaction_to_out,
    _validate_label_ids,
    _validate_source_group_id,
)
from app.schemas.holding import TransactionOut
from app.schemas.transaction import TransactionListItemOut, TransactionListOut, TransactionUpdateIn

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=TransactionListOut)
async def list_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction)
        .join(Holding, Holding.id == Transaction.holding_id)
        .where(Transaction.user_id == current_user.id)
        .options(
            selectinload(Transaction.holding),
            selectinload(Transaction.source_group),
            selectinload(Transaction.transaction_labels),
        )
        .order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
    )
    rows = []
    for tx in result.scalars().all():
        rows.append(
            TransactionListItemOut(
                id=tx.id,
                holding_id=tx.holding_id,
                ticker=tx.holding.ticker,
                holding_name=tx.holding.name,
                type=tx.type,
                transaction_date=tx.transaction_date,
                quantity=tx.quantity,
                price=tx.price,
                amount=tx.quantity * tx.price,
                principal_flow=tx.principal_flow,
                source_group_id=tx.source_group_id,
                source_group_name=tx.source_group.name if tx.source_group else None,
                label_ids=sorted((item.label_id for item in tx.transaction_labels), key=str),
                requires_review=bool(tx.requires_review),
                created_at=tx.created_at,
            )
        )
    return TransactionListOut(transactions=rows)


@router.patch("/{transaction_id}", response_model=TransactionOut)
async def update_transaction(
    transaction_id: uuid.UUID,
    body: TransactionUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .where(Transaction.user_id == current_user.id)
    )
    tx = result.scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    holding = await _get_owned_holding(db, tx.holding_id, current_user.id, lock=True)
    tx = next(item for item in holding.transactions if item.id == transaction_id)
    if tx.type == TransactionType.SELL and body.quantity is not None and body.quantity != tx.quantity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SELL quantity edits require lot allocation editor",
        )
    await _validate_source_group_id(db, current_user.id, body.source_group_id)
    if body.label_ids is not None:
        await _validate_label_ids(db, current_user.id, body.label_ids)
    original_date = tx.transaction_date
    if body.transaction_date is not None:
        tx.transaction_date = body.transaction_date
    if body.quantity is not None:
        tx.quantity = body.quantity
        if tx.buy_lot is not None:
            tx.buy_lot.original_quantity = body.quantity
            tx.buy_lot.remaining_quantity = body.quantity
    if body.price is not None:
        tx.price = body.price
        if tx.buy_lot is not None:
            tx.buy_lot.unit_price = body.price
    if body.principal_flow is not None:
        tx.principal_flow = body.principal_flow
    tx.source_group_id = body.source_group_id
    if tx.buy_lot is not None:
        tx.buy_lot.source_group_id = body.source_group_id
    if body.label_ids is not None:
        await _replace_transaction_labels(db, tx, body.label_ids)
    _replay_and_update_lots(holding)
    _recalculate_holding(holding)
    await _rebuild_snapshots_after_mutation(
        db,
        holding,
        start=min(original_date, tx.transaction_date),
        invalidate_start=min(original_date, tx.transaction_date),
    )
    return _transaction_to_out(tx)
```

Register in `backend/app/main.py`:

```python
from app.routers import transactions

app.include_router(transactions.router)
```

- [ ] **Step 5: GREEN 확인**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_transactions_api.py tests/test_holdings_lots_api.py -q
```

Expected:

- 거래 API 테스트와 기존 holdings lot 테스트 통과.

---

## Task 6: 프론트 타입/API 확장

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Test: `frontend/__tests__/lib/types-dashboard.test.ts` 또는 API 사용 컴포넌트 테스트

- [ ] **Step 1: 타입 사용 실패 테스트 작성**

Create `frontend/__tests__/dashboard/DashboardOverview.test.tsx` with initial type-based fixture:

```tsx
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { GroupPerformanceTable } from '@/components/dashboard/GroupPerformanceTable'
import type { DashboardGroupSummary } from '@/lib/types'

const rows: DashboardGroupSummary[] = [{
  kind: 'source',
  id: 'source-1',
  name: '모음통장',
  color: '#111111',
  summary: {
    total_invested_principal: '1000',
    total_cost_basis: '900',
    total_current_value: '1200',
    total_profit_loss: '200',
    total_profit_loss_pct: '20',
    holding_count: 1,
    accounting_status: 'ok',
    warnings: [],
  },
}]

it('renders group performance metrics with the same summary columns', () => {
  render(<GroupPerformanceTable groups={rows} displayCurrency="KRW" />)

  expect(screen.getByText('투자원금')).toBeInTheDocument()
  expect(screen.getByText('잔여원금')).toBeInTheDocument()
  expect(screen.getByText('평가금액')).toBeInTheDocument()
  expect(screen.getByText('손익')).toBeInTheDocument()
  expect(screen.getByText('손익률')).toBeInTheDocument()
})
```

- [ ] **Step 2: RED 확인**

Run:

```bash
cd frontend && npm test -- DashboardOverview.test.tsx
```

Expected:

- FAIL: `GroupPerformanceTable` 또는 `DashboardGroupSummary` 없음.

- [ ] **Step 3: types 추가**

Modify `frontend/lib/types.ts`:

```ts
export type DisplayCurrency = 'KRW' | 'USD'
export type DashboardGroupKind = 'source' | 'rollup' | 'unclassified'

export interface DashboardExchangeRate {
  base: string
  quote: string
  rate: string
  as_of: string
}

export interface DashboardMetricSummary extends PortfolioCurrencySummary {
  accounting_status: AccountingStatus
  warnings: string[]
}

export interface DashboardGroupSummary {
  kind: DashboardGroupKind
  id: string | null
  name: string
  color: string | null
  summary: DashboardMetricSummary
}

export interface DashboardHistoryPoint {
  snapshot_date: string
  total_value: string | null
  total_invested_principal: string | null
  total_profit_loss: string | null
  accounting_status: AccountingStatus
  warnings: string[]
}

export interface DashboardHistorySeries {
  key: string
  name: string
  kind: DashboardGroupKind | 'all'
  points: DashboardHistoryPoint[]
}

export interface DashboardHoldingGroupBadge {
  source_group_id: string | null
  name: string
  color: string | null
  remaining_quantity: string
}

export interface DashboardHolding extends ScopedPortfolioHolding {
  groups: DashboardHoldingGroupBadge[]
}

export interface DashboardPayload {
  display_currency: DisplayCurrency
  exchange_rate: DashboardExchangeRate | null
  summary: DashboardMetricSummary
  groups: DashboardGroupSummary[]
  history: DashboardHistorySeries[]
  holdings: DashboardHolding[]
  warnings: string[]
}
```

Modify `frontend/lib/api.ts` import and API:

```ts
import type { DashboardPayload, DisplayCurrency, ... } from './types'

export const dashboardApi = {
  path: (displayCurrency: DisplayCurrency) => `/api/portfolio/dashboard?display_currency=${displayCurrency}`,
  get: (displayCurrency: DisplayCurrency) => request<DashboardPayload>(dashboardApi.path(displayCurrency)),
}
```

- [ ] **Step 4: GREEN까지 필요한 최소 컴포넌트 추가**

Create `frontend/components/dashboard/GroupPerformanceTable.tsx`:

```tsx
import { Badge } from '@/components/ui/Badge'
import { cn, formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { DashboardGroupSummary, DisplayCurrency } from '@/lib/types'

interface Props {
  groups: DashboardGroupSummary[]
  displayCurrency: DisplayCurrency
}

export function GroupPerformanceTable({ groups, displayCurrency }: Props) {
  if (groups.length === 0) {
    return <p className="py-8 text-center text-sm text-gray-400">표시할 그룹 수익현황이 없습니다.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50 text-xs font-medium text-gray-500">
            <th className="px-4 py-3 text-left">그룹</th>
            <th className="px-4 py-3 text-right">투자원금</th>
            <th className="px-4 py-3 text-right">잔여원금</th>
            <th className="px-4 py-3 text-right">평가금액</th>
            <th className="px-4 py-3 text-right">손익</th>
            <th className="px-4 py-3 text-right">손익률</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {groups.map((group) => (
            <tr key={`${group.kind}:${group.id ?? 'none'}`} className="hover:bg-gray-50">
              <td className="px-4 py-3"><Badge color={group.color ?? undefined}>{group.name}</Badge></td>
              <td className="px-4 py-3 text-right tabular-nums">{displayMoney(group.summary.total_invested_principal, displayCurrency)}</td>
              <td className="px-4 py-3 text-right tabular-nums">{displayMoney(group.summary.total_cost_basis, displayCurrency)}</td>
              <td className="px-4 py-3 text-right tabular-nums">{displayMoney(group.summary.total_current_value, displayCurrency)}</td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(group.summary.total_profit_loss))}>
                {displayMoney(group.summary.total_profit_loss, displayCurrency)}
              </td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(group.summary.total_profit_loss_pct))}>
                {formatPercent(group.summary.total_profit_loss_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function displayMoney(value: string | null, currency: DisplayCurrency) {
  return value === null ? '—' : formatCurrency(value, currency)
}
```

- [ ] **Step 5: GREEN 확인**

Run:

```bash
cd frontend && npm test -- DashboardOverview.test.tsx
```

Expected:

- 신규 테스트 통과.

---

## Task 7: 대시보드 화면 재구성

**Files:**
- Modify: `frontend/app/page.tsx`
- Create: `frontend/components/dashboard/DashboardOverview.tsx`
- Create: `frontend/components/dashboard/DisplayCurrencyToggle.tsx`
- Create: `frontend/components/dashboard/DashboardChartControls.tsx`
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Modify: `frontend/components/dashboard/HoldingsTable.tsx`
- Test: `frontend/__tests__/dashboard/DashboardOverview.test.tsx`
- Test: `frontend/__tests__/components/HoldingsTable.test.tsx`

- [ ] **Step 1: display toggle 테스트 추가**

Append to `DashboardOverview.test.tsx`:

```tsx
import { fireEvent } from '@testing-library/react'
import { DisplayCurrencyToggle } from '@/components/dashboard/DisplayCurrencyToggle'

it('lets the user switch between KRW converted and USD-only display', () => {
  const onChange = jest.fn()
  render(<DisplayCurrencyToggle value="KRW" onChange={onChange} exchangeRateText="1 USD = 1,380 KRW · 2026-06-04 기준" />)

  fireEvent.click(screen.getByRole('button', { name: 'USD 별도' }))

  expect(onChange).toHaveBeenCalledWith('USD')
  expect(screen.getByText('1 USD = 1,380 KRW · 2026-06-04 기준')).toBeInTheDocument()
})
```

- [ ] **Step 2: RED 확인**

Run:

```bash
cd frontend && npm test -- DashboardOverview.test.tsx
```

Expected:

- FAIL: `DisplayCurrencyToggle` 없음.

- [ ] **Step 3: DisplayCurrencyToggle 구현**

Create `frontend/components/dashboard/DisplayCurrencyToggle.tsx`:

```tsx
import type { DisplayCurrency } from '@/lib/types'

interface Props {
  value: DisplayCurrency
  onChange: (value: DisplayCurrency) => void
  exchangeRateText?: string
}

export function DisplayCurrencyToggle({ value, onChange, exchangeRateText }: Props) {
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex rounded-lg border border-gray-200 bg-white p-1 text-sm">
        {(['KRW', 'USD'] as const).map((currency) => (
          <button
            key={currency}
            type="button"
            onClick={() => onChange(currency)}
            className={`rounded-md px-3 py-1.5 font-medium ${value === currency ? 'bg-brand-500 text-white' : 'text-gray-500 hover:text-gray-900'}`}
          >
            {currency === 'KRW' ? 'KRW 환산' : 'USD 별도'}
          </button>
        ))}
      </div>
      {exchangeRateText && <p className="text-xs text-gray-400">{exchangeRateText}</p>}
    </div>
  )
}
```

- [ ] **Step 4: DashboardOverview 구현**

Create `frontend/components/dashboard/DashboardOverview.tsx`:

```tsx
import Link from 'next/link'
import { Card } from '@/components/ui/Card'
import { DashboardLoadError } from '@/components/dashboard/DashboardLoadError'
import { DisplayCurrencyToggle } from '@/components/dashboard/DisplayCurrencyToggle'
import { GroupPerformanceTable } from '@/components/dashboard/GroupPerformanceTable'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import { PortfolioChart } from '@/components/dashboard/PortfolioChart'
import { PortfolioSummary } from '@/components/dashboard/PortfolioSummary'
import type { DashboardPayload, DisplayCurrency } from '@/lib/types'

interface Props {
  data: DashboardPayload
  displayCurrency: DisplayCurrency
  onDisplayCurrencyChange: (value: DisplayCurrency) => void
  onRetry: () => void
  error?: unknown
}

export function DashboardOverview({ data, displayCurrency, onDisplayCurrencyChange, onRetry, error }: Props) {
  if (error) return <DashboardLoadError onRetry={onRetry} />
  const exchangeRateText = data.exchange_rate
    ? `1 ${data.exchange_rate.base} = ${Number(data.exchange_rate.rate).toLocaleString('ko-KR')} ${data.exchange_rate.quote} · ${data.exchange_rate.as_of} 기준`
    : undefined
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">대시보드</h1>
          <p className="mt-1 text-sm text-gray-500">전체 포트폴리오와 그룹별 수익현황을 함께 봅니다.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <DisplayCurrencyToggle value={displayCurrency} onChange={onDisplayCurrencyChange} exchangeRateText={exchangeRateText} />
          <Link href="/holdings/new" className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600">+ 종목 등록</Link>
        </div>
      </div>
      <PortfolioSummary dashboardSummary={data.summary} displayCurrency={displayCurrency} />
      <Card noPad>
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-semibold text-gray-900">그룹별 수익현황</h2>
          <p className="mt-1 text-xs text-gray-400">통합 그룹은 비교용이며 다른 그룹 행과 단순 합산하면 중복될 수 있습니다.</p>
        </div>
        <GroupPerformanceTable groups={data.groups} displayCurrency={displayCurrency} />
      </Card>
      <Card>
        <h2 className="font-semibold text-gray-900">포트폴리오 변화</h2>
        <PortfolioChart dashboardSeries={data.history} displayCurrency={displayCurrency} />
      </Card>
      <Card noPad>
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-semibold text-gray-900">보유 종목</h2>
        </div>
        <HoldingsTable holdings={data.holdings} />
      </Card>
      <div className="flex justify-end">
        <Link href="/transactions" className="text-sm font-medium text-brand-600 hover:underline">전체 거래내역 보기</Link>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: page.tsx를 aggregate API로 전환**

Modify `frontend/app/page.tsx`:

```tsx
'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { DashboardOverview } from '@/components/dashboard/DashboardOverview'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { dashboardApi, fetcher } from '@/lib/api'
import type { DashboardPayload, DisplayCurrency } from '@/lib/types'

function DashboardContent() {
  const [displayCurrency, setDisplayCurrency] = useState<DisplayCurrency>('KRW')
  const { data, error, isLoading, mutate } = useSWR<DashboardPayload>(
    dashboardApi.path(displayCurrency),
    fetcher,
    { refreshInterval: 30_000 },
  )

  if (isLoading || !data) return <PageLoader />

  return (
    <DashboardOverview
      data={data}
      displayCurrency={displayCurrency}
      onDisplayCurrencyChange={setDisplayCurrency}
      onRetry={() => void mutate()}
      error={error}
    />
  )
}

export default function DashboardPage() {
  return <AuthGuard><DashboardContent /></AuthGuard>
}
```

- [ ] **Step 6: PortfolioSummary dashboard prop 추가**

Modify `frontend/components/dashboard/PortfolioSummary.tsx` to support:

```tsx
type Props =
  | { summary: SummaryPayload; holdings?: never; dashboardSummary?: never; displayCurrency?: never }
  | { holdings: Holding[]; summary?: never; dashboardSummary?: never; displayCurrency?: never }
  | { dashboardSummary: DashboardMetricSummary; displayCurrency: DisplayCurrency; summary?: never; holdings?: never }
```

Add:

```tsx
if (props.dashboardSummary) return <DashboardMetricSummaryCards summary={props.dashboardSummary} displayCurrency={props.displayCurrency} />
```

Use same five-card layout as scoped summary.

- [ ] **Step 7: HoldingsTable group 열 테스트 추가 및 구현**

Append to `frontend/__tests__/components/HoldingsTable.test.tsx`:

```tsx
it('shows source group badges for dashboard holdings', () => {
  render(<HoldingsTable holdings={[{
    holding_id: 'holding-1',
    ticker: '005930',
    name: '삼성전자',
    currency: 'KRW',
    remaining_quantity: '3',
    remaining_cost_basis: '3000',
    current_price: '1200',
    current_value: '3600',
    unrealized_profit_loss: '600',
    groups: [{ source_group_id: 'source-1', name: '모음통장', color: '#111111', remaining_quantity: '3' }],
  }]} />)

  expect(screen.getByText('그룹')).toBeInTheDocument()
  expect(screen.getByText('모음통장 3주')).toBeInTheDocument()
})
```

Implement `groups` support in `HoldingsTable.toRow`.

- [ ] **Step 8: dashboard tests**

Run:

```bash
cd frontend && npm test -- DashboardOverview.test.tsx HoldingsTable.test.tsx PortfolioSummary.test.tsx PortfolioChart.test.ts
```

Expected:

- Targeted frontend tests pass.

---

## Task 8: 전체 거래내역 프론트 화면

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Create: `frontend/app/transactions/page.tsx`
- Create: `frontend/components/transactions/TransactionsTable.tsx`
- Create: `frontend/components/transactions/TransactionFilters.tsx`
- Create: `frontend/components/transactions/TransactionEditPanel.tsx`
- Modify: `frontend/components/layout/Navbar.tsx`
- Test: `frontend/__tests__/transactions/TransactionsPage.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

Create `frontend/__tests__/transactions/TransactionsPage.test.tsx`:

```tsx
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import TransactionsPage from '@/app/transactions/page'

jest.mock('@/components/layout/AuthGuard', () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

jest.mock('swr', () => ({
  __esModule: true,
  default: () => ({
    data: {
      transactions: [{
        id: 'tx-1',
        holding_id: 'holding-1',
        ticker: '005930',
        holding_name: '삼성전자',
        type: 'BUY',
        transaction_date: '2026-06-01',
        quantity: '3',
        price: '1200',
        amount: '3600',
        principal_flow: 'DEPOSIT',
        source_group_id: 'source-1',
        source_group_name: '모음통장',
        label_ids: [],
        requires_review: false,
        created_at: '2026-06-01T00:00:00Z',
      }],
    },
    isLoading: false,
    mutate: jest.fn(),
  }),
}))

it('renders the full transactions page columns', () => {
  render(<TransactionsPage />)

  expect(screen.getByRole('heading', { name: '전체 거래내역' })).toBeInTheDocument()
  expect(screen.getByText('삼성전자')).toBeInTheDocument()
  expect(screen.getByText('투자원금처리')).toBeInTheDocument()
  expect(screen.getByText('모음통장')).toBeInTheDocument()
})
```

- [ ] **Step 2: RED 확인**

Run:

```bash
cd frontend && npm test -- TransactionsPage.test.tsx
```

Expected:

- FAIL: `/transactions/page` 없음.

- [ ] **Step 3: types/api 추가**

Add to `frontend/lib/types.ts`:

```ts
export interface TransactionListItem {
  id: string
  holding_id: string
  ticker: string
  holding_name: string
  type: TxType
  transaction_date: string
  quantity: string
  price: string
  amount: string
  principal_flow: PrincipalFlow
  source_group_id: string | null
  source_group_name: string | null
  label_ids: string[]
  requires_review: boolean
  created_at: string
}

export interface TransactionListPayload {
  transactions: TransactionListItem[]
}
```

Add to `frontend/lib/api.ts`:

```ts
export const transactionsApi = {
  listPath: () => '/api/transactions',
  update: (id: string, data: Partial<TransactionListItem>) =>
    request<Transaction>(`/api/transactions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
}
```

- [ ] **Step 4: page/table 구현**

Create `frontend/app/transactions/page.tsx`:

```tsx
'use client'

import useSWR from 'swr'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { TransactionsTable } from '@/components/transactions/TransactionsTable'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { fetcher, transactionsApi } from '@/lib/api'
import type { TransactionListPayload } from '@/lib/types'

function TransactionsContent() {
  const { data, isLoading, mutate } = useSWR<TransactionListPayload>(transactionsApi.listPath(), fetcher)
  if (isLoading || !data) return <PageLoader />
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">전체 거래내역</h1>
        <p className="mt-1 text-sm text-gray-500">모든 종목의 매수/매도 거래를 조회하고 수정합니다.</p>
      </div>
      <Card noPad>
        <TransactionsTable transactions={data.transactions} onRefresh={() => mutate()} />
      </Card>
    </div>
  )
}

export default function TransactionsPage() {
  return <AuthGuard><TransactionsContent /></AuthGuard>
}
```

Create `frontend/components/transactions/TransactionsTable.tsx`:

```tsx
import Link from 'next/link'
import { Badge } from '@/components/ui/Badge'
import { formatCurrency, formatDate, formatNumber } from '@/lib/utils'
import type { TransactionListItem } from '@/lib/types'

interface Props {
  transactions: TransactionListItem[]
  onRefresh: () => void
}

export function TransactionsTable({ transactions }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50 text-xs font-medium text-gray-500">
            <th className="px-4 py-3 text-left">주문일</th>
            <th className="px-4 py-3 text-left">종목</th>
            <th className="px-4 py-3 text-left">주문</th>
            <th className="px-4 py-3 text-left">그룹</th>
            <th className="px-4 py-3 text-left">투자원금처리</th>
            <th className="px-4 py-3 text-right">수량</th>
            <th className="px-4 py-3 text-right">단가</th>
            <th className="px-4 py-3 text-right">금액</th>
            <th className="px-4 py-3 text-left">상태</th>
            <th className="px-4 py-3 text-right">작업</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {transactions.map((tx) => (
            <tr key={tx.id} className="hover:bg-gray-50">
              <td className="px-4 py-3">{formatDate(tx.transaction_date)}</td>
              <td className="px-4 py-3"><Link href={`/holdings/${tx.holding_id}`} className="font-medium text-gray-900 hover:text-brand-600">{tx.holding_name}</Link><div className="text-xs text-gray-400">{tx.ticker}</div></td>
              <td className="px-4 py-3"><Badge>{tx.type === 'BUY' ? '매수' : '매도'}</Badge></td>
              <td className="px-4 py-3">{tx.source_group_name ?? '미분류'}</td>
              <td className="px-4 py-3">{principalFlowLabel(tx.principal_flow)}</td>
              <td className="px-4 py-3 text-right tabular-nums">{formatNumber(tx.quantity, 0)}</td>
              <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(tx.price, 'KRW')}</td>
              <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(tx.amount, 'KRW')}</td>
              <td className="px-4 py-3">{tx.requires_review ? <Badge className="border-amber-200 bg-amber-50 text-amber-700">검토 필요</Badge> : '정상'}</td>
              <td className="px-4 py-3 text-right"><Link href={`/holdings/${tx.holding_id}`} className="text-sm text-brand-600 hover:underline">수정</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function principalFlowLabel(flow: TransactionListItem['principal_flow']) {
  if (flow === 'DEPOSIT') return '입금'
  if (flow === 'REINVEST') return '재투자'
  return '출금'
}
```

- [ ] **Step 5: Navbar 링크 추가**

Modify `frontend/components/layout/Navbar.tsx` to include:

```tsx
{ href: '/transactions', label: '거래내역' }
```

- [ ] **Step 6: GREEN 확인**

Run:

```bash
cd frontend && npm test -- TransactionsPage.test.tsx
```

Expected:

- 신규 거래내역 페이지 테스트 통과.

---

## Task 9: 종목 상세 수익현황과 그룹별 보유

**Files:**
- Modify: `backend/app/schemas/holding.py`
- Modify: `backend/app/routers/holdings.py`
- Create: `frontend/components/holdings/HoldingPerformanceSummary.tsx`
- Create: `frontend/components/holdings/HoldingGroupBreakdown.tsx`
- Modify: `frontend/app/holdings/[id]/page.tsx`
- Test: `backend/tests/test_holding_detail_performance.py`
- Test: `frontend/__tests__/holdings/HoldingPage.test.tsx`

- [ ] **Step 1: backend 실패 테스트 작성**

Create `backend/tests/test_holding_detail_performance.py`:

```python
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import uuid

from app.models.group import BuyLot
from app.models.holding import Currency, Holding, Market, PrincipalFlow, Transaction, TransactionType
from app.routers.holdings import _holding_performance


def _holding_with_buy():
    holding = Holding(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        ticker="005930",
        market=Market.KRX,
        name="삼성전자",
        quantity=Decimal("2"),
        avg_price=Decimal("1000"),
        currency=Currency.KRW,
        first_buy_date=date(2026, 6, 1),
        is_active=True,
        transactions=[],
        buy_lots=[],
    )
    tx = Transaction(
        id=uuid.uuid4(),
        holding_id=holding.id,
        holding=holding,
        user_id=holding.user_id,
        source_group_id=None,
        type=TransactionType.BUY,
        quantity=Decimal("2"),
        price=Decimal("1000"),
        transaction_date=date(2026, 6, 1),
        principal_flow=PrincipalFlow.DEPOSIT,
        created_at=SimpleNamespace(isoformat=lambda: "2026-06-01T00:00:00+00:00"),
        transaction_labels=[],
        sell_allocations=[],
    )
    lot = BuyLot(
        id=uuid.uuid4(),
        transaction_id=tx.id,
        holding_id=holding.id,
        transaction=tx,
        holding=holding,
        user_id=holding.user_id,
        source_group_id=None,
        original_quantity=Decimal("2"),
        remaining_quantity=Decimal("2"),
        unit_price=Decimal("1000"),
    )
    tx.buy_lot = lot
    holding.transactions = [tx]
    holding.buy_lots = [lot]
    return holding


def test_holding_performance_uses_principal_flow_for_profit():
    holding = _holding_with_buy()

    performance = _holding_performance(holding, Decimal("1200"))

    assert performance.total_invested_principal == Decimal("2000")
    assert performance.total_current_value == Decimal("2400")
    assert performance.total_profit_loss == Decimal("400")
```

- [ ] **Step 2: RED 확인**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_holding_detail_performance.py -q
```

Expected:

- FAIL: `_holding_performance` import 실패.

- [ ] **Step 3: holding schema 확장**

Modify `backend/app/schemas/holding.py`:

```python
class HoldingGroupBreakdownOut(BaseModel):
    source_group_id: uuid.UUID | None
    name: str
    color: str | None = None
    remaining_quantity: Decimal
    remaining_cost_basis: Decimal


class HoldingPerformanceOut(BaseModel):
    total_invested_principal: Decimal | None
    total_cost_basis: Decimal | None
    total_current_value: Decimal | None
    total_profit_loss: Decimal | None
    total_profit_loss_pct: Decimal | None
    groups: list[HoldingGroupBreakdownOut]
```

Add to `HoldingDetailOut`:

```python
performance: HoldingPerformanceOut | None = None
```

- [ ] **Step 4: backend performance 계산**

Modify `backend/app/routers/holdings.py`:

```python
from app.schemas.holding import HoldingPerformanceOut, HoldingGroupBreakdownOut
from app.services.lot_accounting import PortfolioScope, build_current_positions, invested_principal_by_currency
```

Add:

```python
def _holding_performance(holding: Holding, current_price: Decimal | None) -> HoldingPerformanceOut:
    transactions = [_to_accounting_transaction(holding, transaction) for transaction in holding.transactions]
    replay_result = replay(transactions, PortfolioScope("all"))
    positions = build_current_positions(replay_result, {holding.ticker: current_price})
    total_cost_basis = sum((position.remaining_cost_basis for position in positions), ZERO)
    total_current_value = (
        sum((position.current_value for position in positions if position.current_value is not None), ZERO)
        if all(position.current_value is not None for position in positions)
        else None
    )
    invested = invested_principal_by_currency(transactions).get(holding.currency.value, ZERO)
    profit = total_current_value - invested if total_current_value is not None else None
    return HoldingPerformanceOut(
        total_invested_principal=invested,
        total_cost_basis=total_cost_basis,
        total_current_value=total_current_value,
        total_profit_loss=profit,
        total_profit_loss_pct=(profit / invested * 100 if profit is not None and invested > 0 else None),
        groups=[
            HoldingGroupBreakdownOut(
                source_group_id=position.source_group_id,
                name="미분류",
                color=None,
                remaining_quantity=position.remaining_quantity,
                remaining_cost_basis=position.remaining_cost_basis,
            )
            for position in positions
        ],
    )
```

Add `performance=_holding_performance(holding, current_price)` to `HoldingDetailOut`.

- [ ] **Step 5: frontend HoldingPage 테스트 수정**

Modify `frontend/__tests__/holdings/HoldingPage.test.tsx` fixture:

```tsx
performance: {
  total_invested_principal: '200',
  total_cost_basis: '200',
  total_current_value: '240',
  total_profit_loss: '40',
  total_profit_loss_pct: '20',
  groups: [{ source_group_id: null, name: '미분류', color: null, remaining_quantity: '2', remaining_cost_basis: '200' }],
},
```

Add test:

```tsx
it('renders holding performance summary and a single price chart section', () => {
  render(<HoldingPage params={{ id: 'holding-1' }} />)

  expect(screen.getByText('종목 수익현황')).toBeInTheDocument()
  expect(screen.getByText('투자원금')).toBeInTheDocument()
  expect(screen.getByText('그룹별 보유')).toBeInTheDocument()
})
```

- [ ] **Step 6: frontend components 구현**

Create `frontend/components/holdings/HoldingPerformanceSummary.tsx` using the same card labels:

```tsx
import { Card, CardTitle } from '@/components/ui/Card'
import { cn, formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { Currency, HoldingPerformance } from '@/lib/types'

export function HoldingPerformanceSummary({ performance, currency }: { performance: HoldingPerformance; currency: Currency }) {
  const cards = [
    ['투자원금', formatCurrency(performance.total_invested_principal, currency)],
    ['잔여원금', formatCurrency(performance.total_cost_basis, currency)],
    ['평가금액', performance.total_current_value ? formatCurrency(performance.total_current_value, currency) : '—'],
    ['손익', performance.total_profit_loss ? formatCurrency(performance.total_profit_loss, currency) : '—'],
    ['손익률', formatPercent(performance.total_profit_loss_pct)],
  ] as const
  return (
    <section>
      <h2 className="mb-3 font-semibold text-gray-900">종목 수익현황</h2>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {cards.map(([title, value]) => (
          <Card key={title}>
            <CardTitle>{title}</CardTitle>
            <p className={cn('mt-2 text-xl font-bold tabular-nums text-gray-900', title.includes('손익') && profitColor(performance.total_profit_loss))}>{value}</p>
          </Card>
        ))}
      </div>
    </section>
  )
}
```

Create `HoldingGroupBreakdown.tsx` with group rows.

- [ ] **Step 7: HoldingPage 적용**

Modify `frontend/app/holdings/[id]/page.tsx`:

- 기존 `P&L Summary` 4-card block을 `HoldingPerformanceSummary`로 교체한다.
- 가격 차트 Card는 1개만 유지한다.
- 차트 옆 또는 아래에 `HoldingGroupBreakdown`을 추가한다.

- [ ] **Step 8: 종목 상세 테스트**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_holding_detail_performance.py tests/test_holdings_lots_api.py -q
cd frontend && npm test -- HoldingPage.test.tsx
```

Expected:

- Backend and frontend holding detail tests pass.

---

## Task 10: 통합 검증과 서비스 반영

**Files:**
- All changed files.

- [ ] **Step 1: 전체 backend 검증**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/
cd backend && .venv/bin/python -m compileall -q app tests
```

Expected:

- 전체 backend 테스트 통과.
- compileall 출력 없음.

- [ ] **Step 2: 전체 frontend 검증**

Run:

```bash
cd frontend && npm test
cd frontend && npm run build
```

Expected:

- 전체 Jest 테스트 통과.
- Next.js production build 통과.

- [ ] **Step 3: diff 검증**

Run:

```bash
git diff --check
git status --short
```

Expected:

- diff check 출력 없음.
- 의도한 변경 파일만 남아 있음.

- [ ] **Step 4: 서비스 재시작**

Run:

```bash
./svc.sh restart
```

Expected:

- PostgreSQL, Redis, backend, frontend 모두 실행 중.
- `http://127.0.0.1:8000/health` 응답.
- `http://localhost:3000` 응답.

- [ ] **Step 5: 브라우저 smoke test**

Browser:

- `http://localhost:3000`
- 대시보드 진입.
- 그룹별 수익현황 표 표시 확인.
- 통화 토글 클릭.
- 보유종목 그룹 열 표시 확인.
- `/transactions` 진입.
- 종목 상세 진입 후 가격 차트 1개와 종목 수익현황 확인.

- [ ] **Step 6: 최종 커밋**

Run:

```bash
git add backend frontend docs scripts
git commit -m "feat: add group dashboard and transaction management"
```

Expected:

- 구현 변경이 하나의 기능 커밋으로 기록된다.

---

## 실행 전략

Subagent-driven implementation 기준 권장 분할:

1. **Backend Aggregate Agent**
   - Owns: `backend/app/services/exchange_rate.py`, `backend/app/schemas/dashboard.py`, dashboard portions of `backend/app/routers/portfolio.py`, `backend/tests/test_dashboard_aggregate.py`, `backend/tests/test_exchange_rate.py`.
2. **Backend Transactions Agent**
   - Owns: `backend/app/schemas/transaction.py`, `backend/app/routers/transactions.py`, transaction registration in `backend/app/main.py`, `backend/tests/test_transactions_api.py`.
3. **Frontend Dashboard Agent**
   - Owns: dashboard components, `frontend/app/page.tsx`, dashboard tests.
4. **Frontend Transactions Agent**
   - Owns: `/transactions` page and transaction components/tests.
5. **Holding Detail Agent**
   - Owns: holding performance backend additions, holding detail frontend components/tests.

Agents must not revert or overwrite edits from other agents. Each agent should report changed files and verification commands run. The main session should integrate, run full tests, restart services, and browser smoke test.

## 자체 검토 결과

- [x] 설계 요구사항 7개가 Task 1-10에 모두 매핑되어 있다.
- [x] 거래내역 “수정” 범위가 명확하다.
- [x] KRW 기본 환산과 USD 별도 표시가 모두 포함되어 있다.
- [x] 그룹별 수익현황 항목은 전체 수익현황과 같은 지표 세트다.
- [x] 종목 상세는 가격 차트 1개만 기본 표시한다.
- [x] 테스트 명령과 기대 결과가 각 task에 있다.
