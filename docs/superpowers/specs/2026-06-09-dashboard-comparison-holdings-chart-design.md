# Dashboard Comparison, Scoped Holdings, and Integrated Chart Design

## Goal

Improve dashboard accuracy and readability in three related areas:

1. Recover a missing prior-trading-day snapshot during dashboard reads so the daily comparison does not silently fall back multiple trading days.
2. Show only the selected group's owned lot share in the dashboard holdings table.
3. Replace the single-metric dashboard chart with an integrated portfolio chart that combines group composition, total value, invested principal, and daily profit change.

## Current Behavior and Root Cause

The dashboard selects `comparison_as_of` as the latest total-history snapshot before `current_price_as_of`. This is a prior available snapshot, not necessarily the immediately preceding trading day.

Daily snapshots are normally saved by the backend scheduler at 15:35 KST on weekdays. A snapshot can be absent when:

- the backend process was not running at the scheduled time;
- a quote lookup failed during the scheduled job;
- the startup backfill did not obtain the missing recent bar.

For example, when the current price date is June 9, 2026 and the June 8 snapshot is absent, the comparison date falls back to June 5, 2026.

## Design

### 1. Read-Time Prior-Trading-Day Snapshot Recovery

Before building the dashboard response:

1. Load holdings and fetch current price quotes.
2. Determine the dashboard current price date using the existing conservative rule: the earliest valid quote date among included active holdings.
3. For each active holding, inspect snapshots before that current price date.
4. If recent history does not establish a snapshot for the prior available market trading day, request a short price-history window ending one day before the current price date and add missing snapshots using historical quantities.
5. Commit added snapshots and reload holdings before building dashboard history.

The recovery is bounded to the recent comparison window and runs only when the required recent snapshot is absent. It does not rebuild complete holding history on every dashboard request.

If recovery fails for any holding, the dashboard still responds using the latest available comparison snapshot and adds a warning. The UI label becomes `비교 기준(직전 거래일)` so users can see both the intended meaning and the actual date used.

### 2. Selected-Group Holdings Values

The dashboard response will expose holdings for each portfolio group scope, not only all-portfolio holdings.

For the selected scope:

- Source group: include only remaining lots assigned to that source group.
- Combined group: include remaining lots from its member source groups.
- Unclassified: include only remaining lots without a source group.
- Total: include all remaining lots.

Each scoped holding row contains the scoped remaining quantity, remaining cost basis, current value, and unrealized profit/loss. The dashboard holdings table switches to the selected scope's rows. This prevents a stock shared by multiple groups from displaying its full-portfolio quantity and value under one selected group.

### 3. Integrated Portfolio Chart

The main dashboard chart uses synchronized upper and lower panels.

Upper panel:

- Stacked histogram by date for source-group and unclassified current values.
- Solid line for total portfolio value.
- Dashed line for invested principal.

The stacked histogram excludes combined groups because they overlap their member source groups. Its stack total therefore represents the non-overlapping total portfolio composition.

Lower panel:

- Histogram of daily total-profit change.
- Daily total-profit change is `current trading-day total_profit_loss - previous trading-day total_profit_loss`.
- Positive values are green and negative values are red.

Formatting:

- Price axes and tooltips use thousands separators.
- Monetary values display no decimal places.
- Existing chart range control remains.
- When a group filter is selected, the chart shows that scope's value and principal lines plus its daily-profit-change histogram. The group-composition stack is shown only for the total scope.
- Existing combined/separate and single-metric controls are removed because the integrated chart establishes a single primary view.

### 4. Data Contract

Add scoped holdings to each `DashboardGroupSummary` as a `holdings` field. This keeps the summary, history identity, and holdings scope aligned.

Chart data continues to derive from `DashboardHistoryRow`:

- total/source/unclassified history rows provide the non-overlapping stack;
- selected total or group rows provide value, principal, and total-profit series;
- daily profit change is derived client-side from consecutive selected-scope history rows.

No new persisted chart data is required.

## Error Handling

- Snapshot recovery failures do not fail the dashboard request.
- Recovery warnings identify that the prior-trading-day snapshot could not be refreshed.
- Existing quote and exchange-rate warnings remain unchanged.
- If chart series values are unavailable, the chart omits those points and retains the existing empty-state behavior when no usable values exist.

## Testing

Backend tests:

- read-time recovery adds a missing prior-trading-day snapshot and reloads holdings;
- recovery is skipped when the required snapshot already exists;
- recovery failure returns a dashboard with a warning and existing comparison date;
- source, combined, and unclassified group summaries expose holdings calculated only from matching remaining lots.

Frontend tests:

- selecting a group displays scoped holding quantities and values;
- integrated chart builders create total value, principal, non-overlapping group stack, and daily profit-change series;
- combined groups are excluded from stacked group composition;
- money axis/tooltip formatting adds separators and removes decimals;
- the comparison label reads `비교 기준(직전 거래일)`.

## Scope Boundaries

- Keep the existing scheduled snapshot job; read-time recovery supplements it.
- Do not add market-calendar infrastructure. The short historical-price response determines the prior available market trading day.
- Do not include combined groups in stacked chart composition.
- Do not add long-range daily/weekly/monthly aggregation in this change.
