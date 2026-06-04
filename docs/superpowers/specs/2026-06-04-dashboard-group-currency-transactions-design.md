# Dashboard Group, Currency, and Transaction Redesign

## Context

Stockfolio already supports transaction-level source groups, rollup groups, labels, principal-flow accounting, scoped dashboard summary, scoped holdings, and scoped history. The current dashboard is still optimized for one selected scope at a time. The next redesign should let a user keep the whole portfolio in view while comparing groups, seeing KRW-converted totals, and navigating to a complete transaction management screen.

The user approved the A layout direction from the visual mockups:

- Dashboard: keep the whole-portfolio summary as the primary view, then add a group comparison section using the same summary metrics.
- Holding detail: remove duplicate-looking charts and use a single price chart with dashboard-like performance summary cards.

## Goals

1. Show whole-portfolio and group-level performance together on the dashboard.
2. Use the same metric vocabulary everywhere: invested principal, remaining cost basis, current value, profit/loss, profit/loss percentage.
3. Show all default dashboard amounts in KRW by converting USD assets with exchange-rate data.
4. Allow a USD-only mode that shows USD metrics and charts separately.
5. Add group visibility to the holdings table.
6. Add a complete transaction list/editing screen.
7. Simplify holding detail charts and add performance summary information there.

## Non-Goals

- Do not add broker integration or Toss Securities API integration in this pass.
- Do not add advanced analytics such as benchmark comparison, tax lots beyond the existing buy-lot model, or risk metrics.
- Do not redesign authentication or sharing in this pass.
- Do not support direct sell lot allocation editing inside a dense global table row. Sell allocation changes require the existing lot-selection UI pattern and should open an expanded edit panel or route to the holding detail transaction editor.

## Dashboard Design

### Overall Layout

The dashboard uses the approved A layout:

1. Header with page title, display currency toggle, and add-holding action.
2. Whole-portfolio summary cards.
3. Group performance table using the same metrics as the whole summary.
4. Chart area with a view-mode toggle.
5. Holdings table with a group column.
6. Recent transactions preview and link to the full transaction management screen.

### Whole-Portfolio Summary

Cards:

- 투자원금: net external invested principal.
- 잔여원금: remaining lot cost basis.
- 평가금액: current market value.
- 손익: current value minus invested principal.
- 손익률: 손익 divided by invested principal.

Default display mode is KRW-converted, including USD assets converted into KRW.

### Group Performance

The group section is not just “group name plus return.” Each row uses the same metric set:

- 그룹
- 투자원금
- 잔여원금
- 평가금액
- 손익
- 손익률

Rows include:

- Source groups.
- Rollup groups.
- Unclassified, when unclassified lots or transactions exist.

Labels are not shown in the default group performance table in this implementation. Source and rollup groups are the user’s primary “fund source / combined family view” model. Showing labels here by default would create too much overlap.

Rollup rows can overlap source rows. The UI must show a small note that group rows are for comparison and are not meant to be summed together.

### Chart Modes

The chart area supports:

- 하나의 차트: plot whole portfolio and selected group rows together on one chart.
- 그룹별 각각: render one small chart per selected group.

Chart metric selector:

- 평가금액
- 투자원금
- 손익

Default chart:

- KRW display mode: one KRW-converted chart.
- USD display mode: USD-only chart.

The existing mixed KRW/USD dual-axis chart should be replaced for the dashboard default because the user explicitly wants all amounts in KRW by default. USD-only remains available via display mode.

### Currency Display

Display modes:

- KRW 환산: default. KRW assets are unchanged; USD assets are converted using exchange-rate data.
- USD 별도: only USD assets are included, with USD formatting and USD chart values.

The UI must show the exchange-rate basis near the toggle:

- Example: `기준통화: KRW 환산 · 1 USD = 1,380 KRW · 2026-06-04 기준`.

If exchange-rate lookup fails:

- KRW-only values remain visible.
- Converted KRW totals that depend on USD are marked unavailable.
- A warning explains that USD conversion is temporarily unavailable.

### Holdings Table

Add a group column.

For a holding with remaining lots in multiple source groups, show compact badges:

- `모음통장 7주`
- `긴급통장 13주`

For rollups, the holdings table does not need to show rollup membership by default because rollups are derived. Source group badges are the clearest representation of where remaining lots belong.

## Transaction Management Screen

Add a full transaction management page, recommended route:

- `/transactions`

Default columns:

- 주문일
- 종목
- 주문
- 그룹
- 투자원금처리
- 수량
- 단가
- 금액
- 라벨
- 상태
- 작업

Filters:

- Date range.
- Ticker/name search.
- Source group.
- Transaction type.
- Principal flow.
- Review status.

Actions:

- Delete transaction through the existing backend transaction delete behavior.
- Edit transaction group, labels, and principal-flow in place.
- Edit BUY transaction date, quantity, and price through a tested update endpoint that replays lots, recalculates the holding, and rebuilds snapshots.
- Edit SELL transaction price and principal-flow in place because these do not change selected lot quantities.
- Edit SELL transaction quantity or selected lots only through an expanded lot-allocation editor because selected buy lots are required and oversell must be prevented.

## Holding Detail Design

Use the approved A layout:

1. Header with breadcrumb, ticker, market, currency, delete action.
2. 종목 수익현황 cards:
   - 투자원금
   - 잔여원금
   - 평가금액
   - 손익
   - 손익률
3. Single price chart.
4. Group-level holding panel for this ticker.
5. Add transaction form and transaction list.

The duplicate-looking second chart should be removed. A separate performance chart is outside this implementation; if a future implementation adds one, it must be visually and semantically distinct from the price chart.

The holding detail should compute invested principal using only transactions for that holding and the same principal-flow semantics as the dashboard.

## Backend Design

### Portfolio Aggregates

Add a backend dashboard aggregate endpoint that returns whole summary, group summaries, chart series, and holdings enriched with group information in one stable shape.

Recommended endpoint:

- `GET /api/portfolio/dashboard?display_currency=KRW|USD`

Response sections:

- `display_currency`
- `exchange_rate`
- `summary`
- `groups`
- `history`
- `holdings`
- `warnings`

The existing scoped endpoints can remain for sharing and explicit scope views.

### Exchange Rates

Create an exchange-rate service with a small cache. Use the existing `yfinance` dependency to fetch `USDKRW=X` for current USD-to-KRW conversion. If network lookup is unavailable in tests, tests should inject fixed rates.

Minimum behavior:

- `USD -> KRW` rate for current dashboard.
- Historical chart conversion in this implementation uses the latest available rate for clarity and performance, and the response must name that rate basis. Historical daily FX conversion is outside this implementation.

### Transactions

Add a user-owned transaction listing endpoint:

- `GET /api/transactions`

Transaction update endpoint:

- `PATCH /api/transactions/{transaction_id}`

The listing endpoint should return holding metadata, source group metadata, label metadata, principal flow, review status, and computed amount. The update endpoint should enforce the edit boundaries described in the Transaction Management Screen section.

## Frontend Design

New or changed components:

- `DashboardOverview`: orchestrates the new dashboard aggregate payload.
- `DisplayCurrencyToggle`: controls KRW-converted vs USD-only mode.
- `GroupPerformanceTable`: renders group rows with the full metric set.
- `DashboardChartControls`: controls chart mode and metric.
- `HoldingsTable`: add source group badges column.
- `TransactionsPage`: full transaction list, filters, and actions.
- `HoldingPerformanceSummary`: holding-detail summary cards.
- `HoldingGroupBreakdown`: group-level breakdown for one ticker.

Prefer reusing existing formatting helpers and card/table styles.

## Error Handling

- If group accounting requires review, affected group metrics show unavailable values and warnings.
- If a current price is unavailable, affected current value/profit fields are unavailable.
- If USD conversion is unavailable in KRW display mode, show KRW-only data where possible and mark converted whole totals unavailable.
- Transaction edit/delete errors should be shown inline in the row or panel that initiated the action.

## Testing Strategy

Backend:

- Unit tests for KRW conversion aggregation.
- Unit tests for group summary metrics matching whole summary fields.
- API tests for `/api/portfolio/dashboard`.
- API tests for transaction listing ownership and filters.
- Regression tests for principal-flow profit calculation.

Frontend:

- Component tests for group performance table columns.
- Component tests for KRW/USD display toggle behavior.
- Component tests for holdings table group badges.
- Page tests for transaction management filters/actions.
- Holding page test that only one price chart is rendered and summary cards are visible.

## Open Decisions Fixed By This Spec

- Dashboard default is KRW-converted, not dual-axis KRW/USD.
- Group performance rows use the exact same metric set as the whole summary.
- Source groups and rollups are shown in group performance; labels are not included by default.
- Holding detail uses one price chart by default.
- Global transaction edit supports group, labels, principal-flow, BUY date/quantity/price, and SELL price. SELL quantity or selected-lot changes use an expanded lot-allocation editor instead of a dense row edit.
