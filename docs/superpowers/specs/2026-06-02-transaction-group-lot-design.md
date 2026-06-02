# Transaction Group And Lot Tracking Design

## Goal

Track portfolio performance by the actual source of funds for each trade while
also supporting reusable rollup views and overlapping descriptive labels.

Example:

```text
모음통장: 삼성전자 1주 매수
긴급통장: 삼성전자 2주 매수
가족: 모음통장 + 긴급통장
```

The `가족` view must show three shares without duplicating quantities or cost
basis. A sell must explicitly identify the source group and the original buy
lots being reduced.

## Terminology

The existing physical `tags` and `holding_tags` tables represent an MVP that
groups an entire holding. They are not sufficient for the new domain.

The new product language is:

| Concept | Purpose | Cardinality |
| --- | --- | --- |
| Source group | Actual source of funds, such as `모음통장` | One per buy or sell transaction, or unclassified |
| Rollup group | Saved aggregate of source groups, such as `가족` | Contains multiple source groups |
| Label | Overlapping descriptive classification, such as `장기투자` or `공개용` | Zero or more per transaction |
| Buy lot | One recorded purchase with its original and remaining quantity | One per buy transaction |
| Sell lot allocation | Quantity removed from a selected buy lot by a sell | One or more per sell transaction |

Source groups are accounting buckets. Rollup groups are computed views. Labels
are overlapping filters. They must remain separate so totals do not silently
double count.

## User Experience

### Register A Holding

The first purchase form adds:

- A source group selector with `미분류` as the default.
- A multi-select label editor.
- Existing ticker autocomplete, quantity, price, date, and notes fields.

A purchase uses one source group only. If a brokerage order used multiple
sources of funds, the user records separate purchases.

### Add A Purchase

The holding detail page uses the same source group and label controls for each
additional purchase. A new buy lot is created for every recorded purchase.

### Add A Sell

The user:

1. Selects the source group whose shares will be reduced.
2. Sees buy lots in that source group with trade date, remaining quantity, and
   original purchase price.
3. Chooses one or more buy lots and the quantity to reduce from each lot.
4. Optionally selects labels for the sell. The UI suggests labels from the
   selected buy lots but requires confirmation before submission.

The sell is rejected if allocation quantities do not equal the sell quantity,
if a buy lot belongs to another source group, or if any allocation exceeds the
selected lot's remaining quantity.

### Correct A Classification

The transaction list displays source group and labels for every buy and sell.
Each row provides a `분류 수정` action.

Changing the source group or labels of a historical transaction revalidates
all subsequent trades for that holding. The update is rejected if an existing
sell would become invalid. Current-quantity-only group transfers are outside
this scope.

### Manage Groups And Labels

The management screen separates three sections:

- Source groups
- Rollup groups
- Labels

A rollup group selects multiple source groups. Rollup groups cannot contain
other rollup groups in this version. Duplicate members are rejected.

### Dashboard And Sharing

The dashboard supports:

- Entire portfolio
- Unclassified trades
- One source group
- One rollup group
- One label

The same scope applies consistently to the summary, chart, and holdings table.
Shared links can target a source group, rollup group, or label. Shared payloads
must not expose internal IDs or ownership data.

## Data Model

The migration adds the following domain tables. Exact naming may follow the
existing SQLAlchemy style during implementation.

```text
source_groups
- id UUID PK
- user_id UUID FK users.id
- name VARCHAR(50)
- color VARCHAR(7)
- description TEXT NULL
- share_token VARCHAR(36) NULL UNIQUE
- share_requires_auth BOOLEAN
- created_at, updated_at

rollup_groups
- id UUID PK
- user_id UUID FK users.id
- name VARCHAR(50)
- color VARCHAR(7)
- description TEXT NULL
- share_token VARCHAR(36) NULL UNIQUE
- share_requires_auth BOOLEAN
- created_at, updated_at

rollup_group_members
- rollup_group_id UUID FK rollup_groups.id
- source_group_id UUID FK source_groups.id
- PK (rollup_group_id, source_group_id)

labels
- id UUID PK
- user_id UUID FK users.id
- name VARCHAR(50)
- color VARCHAR(7)
- description TEXT NULL
- share_token VARCHAR(36) NULL UNIQUE
- share_requires_auth BOOLEAN
- created_at, updated_at

buy_lots
- id UUID PK
- transaction_id UUID FK transactions.id UNIQUE
- holding_id UUID FK holdings.id
- user_id UUID FK users.id
- source_group_id UUID FK source_groups.id NULL
- original_quantity NUMERIC(20, 6)
- remaining_quantity NUMERIC(20, 6)
- unit_price NUMERIC(20, 6)
- created_at, updated_at

sell_lot_allocations
- id UUID PK
- sell_transaction_id UUID FK transactions.id
- buy_lot_id UUID FK buy_lots.id
- quantity NUMERIC(20, 6)
- created_at
- UNIQUE (sell_transaction_id, buy_lot_id)

transaction_labels
- transaction_id UUID FK transactions.id
- label_id UUID FK labels.id
- PK (transaction_id, label_id)
```

`NULL source_group_id` means `미분류`. It is a product-visible virtual bucket,
not a mutable database row.

All state-changing endpoints verify that the holding, transaction, lot, group,
label, and current user have the same owner. Backdated edits and deletes lock
the affected holding before replaying its trades.

## Accounting Rules

### Buy

Each buy creates one buy lot:

```text
original_quantity = transaction.quantity
remaining_quantity = transaction.quantity
unit_price = transaction.price
source_group = selected source group or unclassified
```

### Sell

A sell stores the user's selected buy lot allocations. Realized profit and
loss uses each selected lot's actual purchase price:

```text
released cost = sum(allocation quantity * buy lot unit price)
realized profit/loss = sell proceeds - released cost
```

Fees are outside the current product scope because existing transactions do
not record fees.

### Current Position

For each ticker and scope:

```text
remaining quantity = sum(matching buy lot remaining quantity)
remaining cost basis = sum(remaining quantity * buy lot unit price)
current value = remaining quantity * current price
unrealized profit/loss = current value - remaining cost basis
```

The full holding remains a sum of all source groups and unclassified lots.

### Scope Rules

- Source group: include lots whose `source_group_id` matches.
- Rollup group: include lots whose source group is one of the rollup members.
- Unclassified: include lots with no source group.
- Label: replay transactions carrying that label. The sell form suggests
  labels inherited from the selected lots so label views stay coherent.
- Entire portfolio: include all lots once, regardless of labels.

Rollup groups never copy lots and labels never alter accounting ownership.

## Historical Chart

The dashboard renders KRW and USD on one chart with separate axes:

- Left axis: KRW
- Right axis: USD
- Distinct series colors and legend entries
- No direct KRW plus USD summation without an FX-rate history

For each trading date and scope, the history engine replays transactions in a
stable `(transaction_date, created_at, id)` order and values remaining lots at
the official closing price. When a ticker lacks a close for a date, the engine
carries forward the most recent prior close and never uses a future close.

The chart exposes:

- `보유자산 평가금액`
- `잔여 원금`
- `평가손익`

Cash balances and post-sell NAV are outside this scope.

Daily snapshots remain ticker close-price records. Historical quantities,
cost basis, and scoped totals are derived from transactions and lots rather
than treated as authoritative snapshot values.

## Migration

Create a new Alembic revision after `1ea62c42a6ce`. Do not edit the initial
schema migration.

Migration behavior:

1. Convert each existing buy transaction into one buy lot.
2. If a holding has no legacy `holding_tags`, use `미분류`.
3. If a holding has exactly one legacy `holding_tags` row, create or reuse a
   source group with the legacy tag's metadata and assign its buy lots.
4. If a holding has multiple legacy `holding_tags` rows, use `미분류`. The UI
   highlights these transactions for manual classification.
5. Preserve legacy tables during the expand phase until new reads and writes
   are verified.
6. Existing sell transactions are marked for review when their lot allocation
   cannot be inferred without ambiguity. New scoped reports must clearly flag
   unresolved legacy sells instead of guessing.
7. Remove legacy `holding_tags` only in a later contract migration after
   production verification.

The current local dataset has one holding and one buy transaction connected to
two legacy groups. It therefore migrates to one unclassified buy lot.

## Error Handling And Integrity

- Reject a sell when selected lots do not cover the exact transaction quantity.
- Reject a sell allocation that exceeds a lot's remaining quantity.
- Reject source-group changes that invalidate later sell allocations.
- Reject rollup group nesting and duplicate rollup members.
- Reject deleting a source group, label, or rollup group while it is referenced.
- Reject soft-deleting a holding with a positive remaining quantity.
- Rebuild or invalidate affected derived history after backdated edits.
- Keep active and inactive holding rules consistent across summary and history.
- Treat quote-provider failures as explicit unavailable prices rather than zero.

## Security

- Check ownership at every group, label, lot, allocation, and holding boundary.
- Use UUID share tokens and preserve the existing optional authentication gate.
- Do not expose internal IDs from public share payloads.
- Add cross-user tests for every new state-changing endpoint.
- Keep SMTP credentials and production secrets outside version control.
- Review CSRF or Origin protection for cookie-authenticated mutations before
  production exposure.

## Testing Strategy

Backend tests cover:

- Buy lot creation for classified and unclassified purchases.
- Same ticker purchased from two source groups.
- Partial and full selected-lot sells.
- Multi-lot sells within one source group.
- Rejection of cross-group lot selection and overselling.
- Historical classification edits and subsequent-trade revalidation.
- Source, rollup, label, unclassified, and full-portfolio summaries.
- Source, rollup, label, unclassified, and full-portfolio history.
- Group totals matching the full portfolio without duplicate accounting.
- Missing-close carry-forward behavior.
- Stable same-day transaction ordering.
- Existing-data migration, including multi-group legacy holdings.
- Cross-user access rejection.
- Public and authentication-required share links.

Frontend tests cover:

- Source-group and label inputs on initial and additional buys.
- Selected source-group lot list on sells.
- Allocation sum and lot-capacity validation.
- Transaction classification editing.
- Group-management sections and rollup member selection.
- One chart with distinct KRW and USD axes.
- Scope filters updating summaries, tables, charts, and shares consistently.

Final verification includes Alembic upgrade, complete backend and frontend test
suites, a frontend production build, `git diff --check`, and browser testing on
`https://stock2.realchoi.com`.

## Delivery Sequence

1. Add the expand migration and models.
2. Add a focused lot accounting service with replay tests.
3. Add scoped summary, history, and sharing APIs.
4. Add transaction classification and sell-allocation APIs.
5. Replace holding-level group UI with transaction-level controls.
6. Add group management, scope filters, the dual-axis chart, and shared views.
7. Run migration verification, regression tests, and live browser checks.

Implementation follows Superpowers `writing-plans`,
`subagent-driven-development`, `test-driven-development`, code review, and
verification-before-completion workflows.
