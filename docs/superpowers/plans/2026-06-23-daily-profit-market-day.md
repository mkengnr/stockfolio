# Market-Day Daily Profit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace misleading `전일대비` portfolio labels with market-local `당일손익`, contributing zero for a market until that market has a quote dated today.

**Architecture:** Add one pure market-local date helper to the existing market-session service. Gate each holding's existing value-change calculation in the backend using its market and provider `price_date`, aggregate those gated values as today, and expose an additive per-market active-status map so the frontend can explain each market's basis without independently interpreting time zones.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, Next.js 14, TypeScript, Jest, Testing Library

---

## File map

- `backend/app/services/market_session.py`: authoritative conversion from UTC `now` to each market's local date.
- `backend/app/routers/portfolio.py`: per-holding daily-profit gating, aggregation, future-date warnings, and per-market activity state.
- `backend/app/schemas/dashboard.py`: additive `daily_change_active_by_market` response field.
- `backend/tests/test_market_session.py`: pure timezone/date boundary tests.
- `backend/tests/test_dashboard_aggregate.py`: KRX/US mixed-market daily-profit behavior and response metadata tests.
- `frontend/lib/types.ts`: TypeScript shape for the additive response field.
- `frontend/components/dashboard/PortfolioSummary.tsx`: summary-card label.
- `frontend/components/dashboard/GroupPerformanceTable.tsx`: group-table label.
- `frontend/components/dashboard/HoldingsTable.tsx`: holding-table label.
- `frontend/components/dashboard/DashboardOverview.tsx`: per-market daily-profit basis text.
- `frontend/__tests__/components/PortfolioSummary.test.tsx`: summary label regression.
- `frontend/__tests__/components/HoldingsTable.test.tsx`: holding label regression.
- `frontend/__tests__/dashboard/DashboardOverview.test.tsx`: mixed active/inactive market basis rendering.
- `frontend/__tests__/share/SharePage.test.tsx`: shared-dashboard label regression.

### Task 1: Market-local date policy

**Files:**
- Modify: `backend/app/services/market_session.py`
- Test: `backend/tests/test_market_session.py`

- [ ] **Step 1: Write failing market-local date tests**

Add tests proving one UTC instant belongs to different KRX and US market dates:

```python
def test_market_local_date_uses_each_market_timezone():
    now = datetime(2026, 6, 22, 23, 0, tzinfo=timezone.utc)

    assert market_local_date(Market.KRX, now) == date(2026, 6, 23)
    assert market_local_date(Market.US, now) == date(2026, 6, 22)
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_market_session.py::test_market_local_date_uses_each_market_timezone -q
```

Expected: FAIL because `market_local_date` is not defined/importable.

- [ ] **Step 3: Implement the pure helper**

Add to `backend/app/services/market_session.py`:

```python
def market_local_date(market: Market, now: datetime) -> date:
    """Return the calendar date currently in effect for a market."""
    return now.astimezone(_MARKET_TZ[market]).date()
```

Use the helper inside `is_write_confirmed` and `safe_query_end` where they currently repeat `local.date()`.

- [ ] **Step 4: Run market-session tests and verify GREEN**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_market_session.py -q
```

Expected: all market-session tests PASS.

- [ ] **Step 5: Commit the helper**

```bash
git add backend/app/services/market_session.py backend/tests/test_market_session.py
git commit -m "refactor: expose market-local trading date"
```

### Task 2: Gate dashboard daily profit by market date

**Files:**
- Modify: `backend/app/routers/portfolio.py`
- Modify: `backend/app/schemas/dashboard.py`
- Test: `backend/tests/test_dashboard_aggregate.py`

- [ ] **Step 1: Write failing KRX-pre-open and US-active tests**

Add a deterministic mixed-market test with `now=datetime(2026, 6, 22, 23, 0, tzinfo=timezone.utc)`:

```python
def test_daily_profit_uses_each_markets_local_day():
    response = build_dashboard_response(
        holdings=[krx_holding, us_holding],
        source_groups=[],
        rollup_groups=[],
        current_prices={"005930": Decimal("1200"), "AAPL": Decimal("120")},
        current_price_dates={"005930": date(2026, 6, 22), "AAPL": date(2026, 6, 22)},
        display_currency="KRW",
        exchange_rate=RATE,
        now=datetime(2026, 6, 22, 23, 0, tzinfo=timezone.utc),
    )

    rows = {row.ticker: row for row in response.holdings}
    assert rows["005930"].current_value_change == Decimal("0")
    assert rows["AAPL"].current_value_change == Decimal("13800")
    assert response.summary.total_current_value_change == Decimal("13800")
    assert response.daily_change_active_by_market == {"KRX": False, "US": True}
```

Construct `krx_holding` with a 6/19 close of 1100 and `us_holding` with a 6/18 close of 110, quantity one, so only the US `(120 - 110) * 1380` contribution remains active.

- [ ] **Step 2: Write failing missing/future-date tests**

Add assertions that a missing `price_date` produces `None`, while a future market-local date produces `None` plus a warning containing the ticker and future date. Also assert a stale date produces numeric zero even when the historical comparison is older.

```python
assert missing_row.current_value_change is None
assert future_row.current_value_change is None
assert "AAPL 현재가 기준일이 시장 날짜보다 미래입니다: 2026-06-23" in response.warnings
```

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_dashboard_aggregate.py::test_daily_profit_uses_each_markets_local_day \
  tests/test_dashboard_aggregate.py::test_daily_profit_rejects_missing_and_future_price_dates -q
```

Expected: FAIL because `build_dashboard_response` has no `now` argument, stale rows still calculate the last session's change, and the response lacks `daily_change_active_by_market`.

- [ ] **Step 4: Add the response field**

Modify `DashboardResponse`:

```python
daily_change_active_by_market: dict[str, bool] = Field(default_factory=dict)
```

- [ ] **Step 5: Implement per-holding gating**

Import `market_local_date`. Change `_dashboard_holding_value_change` to accept the provider date and clock:

```python
def _dashboard_holding_value_change(
    holding: Holding,
    *,
    quantity: Decimal,
    current_value: Decimal | None,
    display_currency: DisplayCurrency,
    exchange_rate: ExchangeRate | None,
    current_price_date: date | None,
    now: datetime,
) -> Decimal | None:
    if current_value is None or current_price_date is None:
        return None
    today = market_local_date(holding.market, now)
    if current_price_date < today:
        return Decimal(0)
    if current_price_date > today:
        return None
    previous_close_price = _holding_previous_close_price(holding, current_price_date)
    if previous_close_price is None:
        return None
    previous_value = _convert_display_money(
        quantity * previous_close_price,
        holding.currency,
        display_currency,
        exchange_rate,
    )
    return current_value - previous_value if previous_value is not None else None
```

Add `now: datetime | None = None` to `build_dashboard_response`, resolve it once with `now = now or datetime.now(timezone.utc)`, and pass it through `_build_dashboard_holdings`. Do not use `date.today()` as a fallback.

- [ ] **Step 6: Build activity metadata and warnings**

For each market represented by active holdings, set activity to true when at least one non-null provider date equals `market_local_date(market, now)`. Append a ticker-specific warning for every provider date later than the market-local date. Return the map in `DashboardResponse`.

```python
daily_change_active_by_market[market.value] = any(
    price_date == market_local_date(market, now)
    for price_date in market_price_dates
)
```

- [ ] **Step 7: Run dashboard tests and verify GREEN**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py -q
```

Expected: all dashboard aggregate tests PASS after updating legacy fixtures to supply explicit `current_price_dates` and `now` where they assert daily-profit values.

- [ ] **Step 8: Commit backend daily-profit behavior**

```bash
git add backend/app/routers/portfolio.py backend/app/schemas/dashboard.py backend/tests/test_dashboard_aggregate.py
git commit -m "feat: calculate daily profit by market-local day"
```

### Task 3: Rename UI labels and explain market bases

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/components/dashboard/PortfolioSummary.tsx`
- Modify: `frontend/components/dashboard/GroupPerformanceTable.tsx`
- Modify: `frontend/components/dashboard/HoldingsTable.tsx`
- Modify: `frontend/components/dashboard/DashboardOverview.tsx`
- Test: `frontend/__tests__/components/PortfolioSummary.test.tsx`
- Test: `frontend/__tests__/components/HoldingsTable.test.tsx`
- Test: `frontend/__tests__/dashboard/DashboardOverview.test.tsx`
- Test: `frontend/__tests__/share/SharePage.test.tsx`

- [ ] **Step 1: Write failing label tests**

Change/add expectations so every dashboard surface finds `당일손익` and no longer finds `전일대비`:

```typescript
expect(screen.getByText('당일손익')).toBeInTheDocument()
expect(screen.queryByText('전일대비')).not.toBeInTheDocument()
```

For screens with multiple instances, use `getAllByText('당일손익')` and assert the expected count is positive.

- [ ] **Step 2: Write failing mixed-market basis test**

Extend the `DashboardResponse` fixture:

```typescript
daily_change_active_by_market: { KRX: false, US: true },
```

Assert the header renders one combined line:

```typescript
expect(screen.getByText('당일손익 기준: 한국 당일 시세 없음 · 미국 2026-06-22 vs 2026-06-18')).toBeInTheDocument()
```

- [ ] **Step 3: Run focused frontend tests and verify RED**

Run:

```bash
cd frontend && npm test -- --runInBand \
  __tests__/components/PortfolioSummary.test.tsx \
  __tests__/components/HoldingsTable.test.tsx \
  __tests__/dashboard/DashboardOverview.test.tsx \
  __tests__/share/SharePage.test.tsx
```

Expected: FAIL because the UI still says `전일대비` and the TypeScript response lacks the activity map.

- [ ] **Step 4: Add the frontend response type**

Add to `DashboardResponse` in `frontend/lib/types.ts`:

```typescript
daily_change_active_by_market: Record<string, boolean>
```

Update all typed test fixtures with the field.

- [ ] **Step 5: Implement the basis formatter**

In `DashboardOverview.tsx`, format markets in the existing KRX/US display order:

```typescript
function orderedMarketEntries(byMarket: Record<string, string>) {
  const rank = (market: string) => {
    const index = MARKET_ORDER.indexOf(market)
    return index === -1 ? MARKET_ORDER.length : index
  }
  return Object.entries(byMarket).sort((a, b) => rank(a[0]) - rank(b[0]))
}

function formatDailyProfitBasis(dashboard: DashboardResponse) {
  return orderedMarketEntries(dashboard.price_dates_by_market).map(([market, priceDate]) => {
    const label = MARKET_LABELS[market] ?? market
    if (!dashboard.daily_change_active_by_market[market]) return `${label} 당일 시세 없음`
    const comparisonDate = dashboard.comparison_dates_by_market[market]
    return comparisonDate
      ? `${label} ${priceDate} vs ${comparisonDate}`
      : `${label} ${priceDate} 기준`
  }).join(' · ')
}
```

Replace the old comparison line with:

```tsx
<span>당일손익 기준: {formatDailyProfitBasis(dashboard)}</span>
```

- [ ] **Step 6: Rename all dashboard labels**

Replace the user-facing label in `PortfolioSummary`, `GroupPerformanceTable`, and `HoldingsTable` with `당일손익`. Keep internal sort and API property names unchanged.

- [ ] **Step 7: Run focused frontend tests and verify GREEN**

Run the same focused Jest command from Step 3.

Expected: all selected suites PASS. Existing React `act(...)` console warnings may remain but no test may fail.

- [ ] **Step 8: Commit frontend terminology and basis display**

```bash
git add frontend/lib/types.ts frontend/components/dashboard/PortfolioSummary.tsx \
  frontend/components/dashboard/GroupPerformanceTable.tsx \
  frontend/components/dashboard/HoldingsTable.tsx \
  frontend/components/dashboard/DashboardOverview.tsx \
  frontend/__tests__/components/PortfolioSummary.test.tsx \
  frontend/__tests__/components/HoldingsTable.test.tsx \
  frontend/__tests__/dashboard/DashboardOverview.test.tsx \
  frontend/__tests__/share/SharePage.test.tsx
git commit -m "feat: present portfolio movement as daily profit"
```

### Task 4: Regression verification and deployment readiness

**Files:**
- Verify only; no expected source changes

- [ ] **Step 1: Run the complete backend suite**

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Expected: all tests PASS with only the existing deprecation warnings and intentional skips.

- [ ] **Step 2: Run the complete frontend suite and production build**

```bash
cd frontend && npm test -- --runInBand
cd frontend && npm run build
```

Expected: 27 Jest suites PASS and Next.js production build completes successfully. Existing React `act(...)` warnings are non-blocking.

- [ ] **Step 3: Check the patch and branch state**

```bash
git diff --check
git status --short
git log --oneline --decorate -5
```

Expected: no whitespace errors and no uncommitted implementation files.

- [ ] **Step 4: Request code review before deployment**

Review the diff from base `9dca58e` through the final implementation commit for correctness against `docs/superpowers/specs/2026-06-23-daily-profit-market-day-design.md`. Fix every Critical or Important finding and rerun the relevant tests.

- [ ] **Step 5: Deploy only after review approval**

```bash
./svc.sh deploy
```

Expected: build and migration phases succeed, backend and frontend restart healthy. No DB migration or snapshot repair command is expected for this feature.

- [ ] **Step 6: Verify the authenticated dashboard**

At a time when KRX has no quote dated today and US does, verify:

- summary, group, and holdings labels say `당일손익`;
- KRX holding contributions are 0;
- US contributions use the current US market date;
- the header explains `한국 당일 시세 없음` and the US comparison dates;
- summary daily profit equals the sum of holding daily profits.
