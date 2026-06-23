# Live Portfolio Chart Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the latest current-price portfolio state in owner, label, and shared charts while aligning both chart panes by date, exposing top-chart dates, and enabling principal-based gain/loss shading everywhere.

**Architecture:** Keep persisted snapshot history unchanged and build a render-only live point from the existing dashboard summary payload. Merge the live point in shared pure chart-data helpers, normalize the lower histogram onto the same date calendar as the upper chart, and connect both chart surfaces through the existing `PortfolioChart` component. Change only the now-inaccurate intraday warning in the backend.

**Tech Stack:** Next.js 14, React 18, TypeScript, Jest/Testing Library, TradingView Lightweight Charts 4.2, FastAPI/Pydantic, pytest.

---

## File map

- Modify `frontend/components/dashboard/PortfolioChart.tsx`: live-point contract, row merge, aligned whitespace timeline, date-range synchronization, visible upper time axis.
- Modify `frontend/components/dashboard/DashboardOverview.tsx`: pass the selected live summary and current group summaries; enable gain/loss shading.
- Modify `frontend/app/share/[token]/page.tsx`: derive the public live date, pass selected live summary/current groups, and retain shading.
- Modify `frontend/__tests__/dashboard/PortfolioChart.test.ts`: pure merge, live daily-profit, whitespace calendar, and band coverage tests.
- Modify `frontend/__tests__/dashboard/PortfolioChartLegend.test.tsx`: chart option and time-range synchronization tests.
- Modify `frontend/__tests__/dashboard/DashboardOverview.test.tsx`: owner and label live-point/shading wiring tests.
- Modify `frontend/__tests__/share/SharePage.test.tsx`: shared total/group live-point wiring tests.
- Modify `backend/app/routers/portfolio.py`: shorten the intraday warning now that charts include current values.
- Modify `backend/app/routers/groups.py`: update the public-warning allowlist pattern.
- Modify `backend/tests/test_dashboard_aggregate.py`: new intraday warning expectation.
- Modify `backend/tests/test_groups_api.py`: public warning expectation and filtering regression.

### Task 1: Merge the render-only current-price point

**Files:**
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Test: `frontend/__tests__/dashboard/PortfolioChart.test.ts`

- [ ] **Step 1: Write failing pure-data tests**

Add `DashboardSummary` fixture data and tests that prove a current point is appended, replaces a same-date snapshot, is skipped without a date/value, and uses the live daily-profit value:

```ts
const liveSummary: DashboardSummary = {
  total_invested_principal: '600000',
  total_cost_basis: '700000',
  total_current_value: '790000',
  total_current_value_change: '-25000',
  total_current_value_change_pct: '-3.07',
  total_unrealized_profit_loss: '90000',
  total_unrealized_profit_loss_pct: '12.86',
  total_profit_loss: '175000',
  total_profit_loss_pct: '29.17',
}

it('appends a render-only live row and uses the dashboard daily profit', () => {
  const merged = mergeDashboardLivePoint(
    rows.filter((row) => row.group_kind === 'total'),
    {
      snapshotDate: '2026-06-03',
      groupKind: 'total',
      groupId: null,
      groupName: '전체',
      summary: liveSummary,
    },
  )
  expect(merged.rows.at(-1)).toMatchObject({
    snapshot_date: '2026-06-03',
    total_value: '790000',
    total_profit_loss: '175000',
  })
  expect(merged.liveDailyProfit).toBe(-25000)
})

it('replaces a same-date snapshot instead of duplicating it', () => {
  const merged = mergeDashboardLivePoint(
    rows.filter((row) => row.group_kind === 'total'),
    {
      snapshotDate: '2026-06-02',
      groupKind: 'total',
      groupId: null,
      groupName: '전체',
      summary: liveSummary,
    },
  )
  expect(merged.rows.filter((row) => row.snapshot_date === '2026-06-02')).toHaveLength(1)
  expect(merged.rows.at(-1)?.total_value).toBe('790000')
})

it('keeps confirmed history when the live date or value is unavailable', () => {
  const history = rows.filter((row) => row.group_kind === 'total')
  expect(mergeDashboardLivePoint(history, null).rows).toEqual(history)
  expect(mergeDashboardLivePoint(history, {
    snapshotDate: null,
    groupKind: 'total',
    groupId: null,
    groupName: '전체',
    summary: { ...liveSummary, total_current_value: null },
  }).rows).toEqual(history)
})
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd frontend && npm test -- --runInBand __tests__/dashboard/PortfolioChart.test.ts
```

Expected: FAIL because `DashboardLivePoint`/`mergeDashboardLivePoint` do not exist.

- [ ] **Step 3: Add the live-point contract and merge helper**

In `PortfolioChart.tsx`, import `DashboardSummary` and add:

```ts
export interface DashboardLivePoint {
  snapshotDate: string | null
  groupKind: DashboardHistoryGroupKind
  groupId: string | null
  groupName: string
  summary: DashboardSummary
}

export function mergeDashboardLivePoint(
  rows: DashboardHistoryRow[],
  livePoint: DashboardLivePoint | null | undefined,
) {
  const liveValue = livePoint?.summary.total_current_value
  if (!livePoint?.snapshotDate || liveValue === null || liveValue === undefined) {
    return { rows, liveDailyProfit: null as number | null }
  }
  const liveRow: DashboardHistoryRow = {
    group_kind: livePoint.groupKind,
    group_id: livePoint.groupId,
    group_name: livePoint.groupName,
    snapshot_date: livePoint.snapshotDate,
    total_value: liveValue,
    total_invested_principal: livePoint.summary.total_invested_principal,
    total_cost_basis: livePoint.summary.total_cost_basis,
    total_profit_loss: livePoint.summary.total_profit_loss,
  }
  const mergedRows = rows
    .filter((row) => row.snapshot_date !== livePoint.snapshotDate)
    .concat(liveRow)
    .sort((left, right) => left.snapshot_date.localeCompare(right.snapshot_date))
  return {
    rows: mergedRows,
    liveDailyProfit: parseNullableNumber(livePoint.summary.total_current_value_change),
  }
}
```

Keep this helper render-only; do not change API response types or persistence code.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit the pure live-point behavior**

```bash
git add frontend/components/dashboard/PortfolioChart.tsx frontend/__tests__/dashboard/PortfolioChart.test.ts
git commit -m "feat: merge live portfolio point into charts"
```

### Task 2: Align both panes on one date calendar

**Files:**
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Test: `frontend/__tests__/dashboard/PortfolioChart.test.ts`
- Test: `frontend/__tests__/dashboard/PortfolioChartLegend.test.tsx`

- [ ] **Step 1: Write failing timeline tests**

Change the integrated chart-data expectation so daily profit includes whitespace for the first date and accepts a live override:

```ts
expect(data.dailyProfitChange).toEqual([
  { time: '2026-06-01' },
  { time: '2026-06-02', value: 15000, color: '#dc2626' },
  { time: '2026-06-03', value: -25000, color: '#2563eb' },
])
```

Add component mock assertions:

```ts
expect(createChart.mock.calls[0][1].timeScale.visible).toBe(true)
expect(timeScaleApis.some((api) => api.subscribeVisibleTimeRangeChange.mock.calls.length > 0)).toBe(true)
expect(timeScaleApis.some((api) => api.subscribeVisibleLogicalRangeChange.mock.calls.length > 0)).toBe(false)
```

Extend the chart mock with `subscribeVisibleTimeRangeChange`, `unsubscribeVisibleTimeRangeChange`, and retain `setVisibleRange`.

- [ ] **Step 2: Run both chart test files and verify RED**

```bash
cd frontend && npm test -- --runInBand __tests__/dashboard/PortfolioChart.test.ts __tests__/dashboard/PortfolioChartLegend.test.tsx
```

Expected: FAIL because the first profit date is absent, upper `timeScale.visible` is false, and synchronization uses logical ranges.

- [ ] **Step 3: Normalize the lower histogram**

Change the daily-profit type to allow whitespace:

```ts
type DailyProfitChartPoint =
  | { time: string }
  | { time: string; value: number; color: string }
```

Update `buildIntegratedDashboardChartData` to accept `liveDailyProfit?: number | null`. Iterate every ordered selected row and always push one point. Use the confirmed profit delta for historical dates and use `liveDailyProfit` for the final live date when supplied. Preserve red for non-negative values and blue for negative values.

When sending data to Lightweight Charts, map whitespace without inventing a value:

```ts
profitSeries.setData(chartData.dailyProfitChange.map((point) => (
  'value' in point
    ? { time: point.time as Time, value: point.value, color: point.color }
    : { time: point.time as Time }
)))
```

- [ ] **Step 4: Replace logical-range synchronization with time-range synchronization**

Set the upper chart `timeScale.visible` to `true`. Replace `subscribeVisibleLogicalRangeChange` with guarded `subscribeVisibleTimeRangeChange` handlers that call `target.timeScale().setVisibleRange(range)`. Keep the same `rightOffset` on both charts.

Store both handler functions and unsubscribe them in the effect cleanup before removing charts.

- [ ] **Step 5: Run both chart tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 6: Commit aligned dates and upper date labels**

```bash
git add frontend/components/dashboard/PortfolioChart.tsx frontend/__tests__/dashboard/PortfolioChart.test.ts frontend/__tests__/dashboard/PortfolioChartLegend.test.tsx
git commit -m "fix: align portfolio chart dates"
```

### Task 3: Connect owner, label, and shared current points and shading

**Files:**
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Modify: `frontend/components/dashboard/DashboardOverview.tsx`
- Modify: `frontend/app/share/[token]/page.tsx`
- Test: `frontend/__tests__/dashboard/DashboardOverview.test.tsx`
- Test: `frontend/__tests__/share/SharePage.test.tsx`

- [ ] **Step 1: Write failing owner/share wiring tests**

Extend both mocked `PortfolioChart` renderers to expose `livePoint`, `liveComposition`, and `showGainLossBand`. Assert:

```ts
expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('live:2026-06-05:900000:50000')
expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('band:on')
```

For the shared fixture, assert the latest market date is used:

```ts
expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('live:2026-06-23:390:20')
```

After selecting the shared child group, assert `240:10` replaces `390:20` and composition turns off.

Add a label-dashboard case that verifies the label response's date and summary are passed rather than the owner dashboard's values.

- [ ] **Step 2: Run owner/share tests and verify RED**

```bash
cd frontend && npm test -- --runInBand __tests__/dashboard/DashboardOverview.test.tsx __tests__/share/SharePage.test.tsx
```

Expected: FAIL because callers do not pass a live point and the owner does not enable the gain/loss band.

- [ ] **Step 3: Extend `PortfolioChart` props and merge inputs**

Add dashboard-only props:

```ts
livePoint?: DashboardLivePoint | null
liveComposition?: DashboardLivePoint[]
```

Merge `historyRows` with `livePoint` before building the selected series. Convert `liveComposition` summaries into current-date `DashboardHistoryRow` objects and merge them into `compositionRows` with a `(kind,id,date)` key before calling `buildCumulativeComposition`.

- [ ] **Step 4: Wire the owner and label dashboard**

In `DashboardOverview.tsx`, pass:

```tsx
livePoint={activeDashboard ? {
  snapshotDate: activeDashboard.current_price_as_of,
  groupKind: labelMode ? 'total' : (selectedGroup?.kind ?? 'total'),
  groupId: labelMode ? null : (selectedGroup?.id ?? null),
  groupName: selectedName,
  summary: activeSummary!,
} : null}
liveComposition={activeDashboard?.groups.map((group) => ({
  snapshotDate: activeDashboard.current_price_as_of,
  groupKind: group.kind,
  groupId: group.id,
  groupName: group.name,
  summary: group.summary,
})) ?? []}
showGainLossBand
```

Keep `referenceDefault="invested"`. For label mode, use the label response for both the live point and date; composition remains disabled.

- [ ] **Step 5: Wire the shared dashboard**

In the shared page, add a pure local helper that returns the latest valid ISO date from `price_dates_by_market`:

```ts
function latestMarketDate(dates: Record<string, string> | undefined) {
  const values = Object.values(dates ?? {}).filter(Boolean)
  return values.length > 0 ? values.sort().at(-1)! : null
}
```

Pass the selected shared summary as `livePoint`, map public source groups into `liveComposition` using their public keys as IDs, and keep `showGainLossBand` enabled.

- [ ] **Step 6: Run owner/share tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 7: Commit all chart-surface wiring**

```bash
git add frontend/components/dashboard/PortfolioChart.tsx frontend/components/dashboard/DashboardOverview.tsx frontend/app/share/'[token]'/page.tsx frontend/__tests__/dashboard/DashboardOverview.test.tsx frontend/__tests__/share/SharePage.test.tsx
git commit -m "feat: show live values across portfolio charts"
```

### Task 4: Correct intraday warnings for owner and public share

**Files:**
- Modify: `backend/app/routers/portfolio.py`
- Modify: `backend/app/routers/groups.py`
- Test: `backend/tests/test_dashboard_aggregate.py`
- Test: `backend/tests/test_groups_api.py`

- [ ] **Step 1: Update tests first**

Change expected warnings to:

```python
assert warnings == ["KRX 장중 현재가입니다."]
```

and public fixtures to:

```python
public_warnings = [
    "US 일부 종목의 현재가 기준일이 다릅니다: 2026-06-20 ~ 2026-06-22",
    "US 장중 현재가입니다.",
    "USD/KRW exchange rate lookup failed",
]
```

Keep the assertion that internal accounting warnings and unrelated ticker warnings are filtered out.

- [ ] **Step 2: Run focused backend tests and verify RED**

```bash
cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py::test_intraday_market_warning_explains_live_value_vs_confirmed_chart tests/test_groups_api.py::test_public_share_omits_internal_warnings_and_legacy_fields -q
```

Expected: FAIL with the old longer warning.

- [ ] **Step 3: Change the warning producer and public pattern**

In `_intraday_market_warnings`, return:

```python
return [f"{market} 장중 현재가입니다." for market in sorted(intraday_markets)]
```

In `groups.py`, update the allowed intraday warning regex to match exactly `(?:KRX|US) 장중 현재가입니다\.`.

- [ ] **Step 4: Run focused backend tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit the warning correction**

```bash
git add backend/app/routers/portfolio.py backend/app/routers/groups.py backend/tests/test_dashboard_aggregate.py backend/tests/test_groups_api.py
git commit -m "fix: update intraday chart guidance"
```

### Task 5: Full verification and browser QA

**Files:**
- Verify all files changed in Tasks 1-4.

- [ ] **Step 1: Run the complete frontend suite**

```bash
cd frontend && npm test -- --runInBand
```

Expected: all Jest suites PASS.

- [ ] **Step 2: Run the frontend production build**

```bash
cd frontend && npm run build
```

Expected: Next.js build completes successfully with no type errors.

- [ ] **Step 3: Run the complete backend suite**

```bash
cd backend && .venv/bin/python -m pytest tests/
```

Expected: all pytest tests PASS.

- [ ] **Step 4: Deploy using the project service script**

Inspect `svc.sh` usage, then deploy only with its documented deploy command. Confirm frontend and backend health before browser QA.

- [ ] **Step 5: Verify the owner dashboard in the logged-in in-app browser**

Check total and each group at desktop and mobile widths:

- last upper value equals the current summary value;
- last lower bar equals the current daily-profit summary;
- upper and lower dates share the same X position;
- upper hover exposes the date;
- invested/cost toggles change both reference line and band;
- 1m/3m/6m/1y/all retain the live endpoint.

- [ ] **Step 6: Verify a shared page in the in-app browser**

Open an existing share link through the app UI. Verify total and child-group values, aligned dates, upper date hover, and gain/loss shading without exposing internal IDs.

- [ ] **Step 7: Request code review and address findings**

Use `superpowers:requesting-code-review`, fix any correctness findings with focused tests, and rerun the affected suite.

- [ ] **Step 8: Record final verification**

```bash
git status --short --branch
git log -5 --oneline
```

Expected: clean working tree and the Task 1-4 commits present on the feature branch.
