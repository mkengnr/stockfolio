# Transaction Group And Lot Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace holding-level tags with transaction-level source groups, rollup groups, labels, and selected-buy-lot sells while preserving accurate scoped portfolio reporting.

**Architecture:** Keep `Holding` and `Transaction` as the brokerage-level record. Add focused group models and a lot-accounting service that replays immutable buy lots and stored sell allocations. Route summary, history, sharing, and UI scopes through the same accounting concepts so source, rollup, label, unclassified, and full views remain consistent.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16, Pydantic v2, pytest, Next.js 14 App Router, TypeScript, SWR, Jest, TradingView Lightweight Charts

---

## File Structure

Create focused backend modules:

- `backend/app/models/group.py`: source groups, rollup groups, labels, buy lots, sell allocations, and transaction labels.
- `backend/app/services/lot_accounting.py`: pure replay, validation, current-position, and scope-selection helpers.
- `backend/app/routers/groups.py`: authenticated management APIs and shared-scope API.
- `backend/app/schemas/group.py`: input and output contracts for groups, labels, lots, scopes, summaries, and shares.
- `backend/alembic/versions/8b0f6baf8b2a_add_transaction_group_lots.py`: expand migration and conservative legacy backfill.

Keep existing files responsible for their current boundaries:

- `backend/app/routers/holdings.py`: holding and transaction mutations.
- `backend/app/routers/portfolio.py`: scoped portfolio summary and history orchestration.
- `backend/app/services/snapshot_service.py`: close-price storage and history rebuild support.
- `frontend/components/groups/*`: reusable source-group, label, rollup, and lot-selection controls.
- `frontend/components/dashboard/*`: scope filter and dual-axis chart.

Legacy `Tag`, `HoldingTag`, `/api/tags`, and their UI remain available only
during the expand transition. New reads and writes use `/api/groups`.

### Task 1: Expand Migration And Domain Models

**Files:**
- Create: `backend/app/models/group.py`
- Modify: `backend/app/models/holding.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/8b0f6baf8b2a_add_transaction_group_lots.py`
- Test: `backend/tests/test_group_migration.py`

- [ ] **Step 1: Write failing model and migration tests**

Add tests that import all new models, verify table names and relationships, and
run Alembic upgrade against a fixture containing legacy holdings with zero, one,
and two `holding_tags` rows.

```python
def test_multitag_legacy_holding_becomes_unclassified_buy_lot(migrated_connection):
    lot = migrated_connection.execute(
        sa.text("select source_group_id from buy_lots where transaction_id = :tx"),
        {"tx": MULTITAG_BUY_ID},
    ).one()
    assert lot.source_group_id is None


def test_single_tag_legacy_holding_reuses_backfilled_source_group(migrated_connection):
    lot = migrated_connection.execute(
        sa.text("select source_group_id from buy_lots where transaction_id = :tx"),
        {"tx": SINGLE_TAG_BUY_ID},
    ).one()
    assert lot.source_group_id is not None
```

- [ ] **Step 2: Run migration tests and confirm RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_group_migration.py -v
```

Expected: import or relation failures because the new models and migration do
not exist.

- [ ] **Step 3: Add the domain models**

Implement these SQLAlchemy models with ownership indexes, positive-quantity
checks, cascading foreign keys, uniqueness constraints, and relationships:

```python
class SourceGroup(Base):
    __tablename__ = "source_groups"
    id: Mapped[UUID]
    user_id: Mapped[UUID]
    name: Mapped[str]
    color: Mapped[str]
    description: Mapped[str | None]
    share_token: Mapped[str | None]
    share_requires_auth: Mapped[bool]


class RollupGroup(Base):
    __tablename__ = "rollup_groups"
    id: Mapped[UUID]
    user_id: Mapped[UUID]
    name: Mapped[str]


class RollupGroupMember(Base):
    __tablename__ = "rollup_group_members"
    rollup_group_id: Mapped[UUID]
    source_group_id: Mapped[UUID]


class Label(Base):
    __tablename__ = "labels"
    id: Mapped[UUID]
    user_id: Mapped[UUID]
    name: Mapped[str]


class BuyLot(Base):
    __tablename__ = "buy_lots"
    id: Mapped[UUID]
    transaction_id: Mapped[UUID]
    holding_id: Mapped[UUID]
    user_id: Mapped[UUID]
    source_group_id: Mapped[UUID | None]
    original_quantity: Mapped[Decimal]
    remaining_quantity: Mapped[Decimal]
    unit_price: Mapped[Decimal]


class SellLotAllocation(Base):
    __tablename__ = "sell_lot_allocations"
    id: Mapped[UUID]
    sell_transaction_id: Mapped[UUID]
    buy_lot_id: Mapped[UUID]
    quantity: Mapped[Decimal]


class TransactionLabel(Base):
    __tablename__ = "transaction_labels"
    transaction_id: Mapped[UUID]
    label_id: Mapped[UUID]
```

Add `Transaction.buy_lot`, `Transaction.sell_allocations`,
`Transaction.transaction_labels`, and matching `User` relationships.

- [ ] **Step 4: Add the expand migration**

Create tables with `server_default` values for every new non-null column.
Backfill source groups from legacy `tags`, create one `buy_lots` row per legacy
buy transaction, assign a source only when a holding has exactly one legacy
tag, and leave ambiguous lots unclassified. Preserve `tags` and
`holding_tags`. Mark unresolved legacy sells explicitly with a boolean
`requires_review` column on `transactions`, defaulting to false and set true
for pre-migration sell rows.

- [ ] **Step 5: Run migration tests and Alembic verification**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_group_migration.py -v
.venv/bin/alembic upgrade head
.venv/bin/alembic check
```

Expected: PASS and no schema drift.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models backend/alembic/versions backend/tests/test_group_migration.py
git commit -m "feat: add transaction group lot schema"
```

### Task 2: Lot Accounting Replay Service

**Files:**
- Create: `backend/app/services/lot_accounting.py`
- Test: `backend/tests/test_lot_accounting.py`

- [ ] **Step 1: Write failing pure-service tests**

Cover classified and unclassified buys, same ticker in two groups, selected-lot
partial and full sells, a sell spanning multiple lots in one group, cross-group
lot rejection, oversell rejection, stable same-day ordering, scoped rollup
selection, label filtering, and carry-forward closes.

```python
def test_selected_lot_sell_uses_actual_purchase_price():
    result = replay([
        buy("2026-01-01", quantity="1", price="80000", source="savings"),
        buy("2026-01-02", quantity="2", price="90000", source="emergency"),
        sell("2026-02-01", quantity="1", price="100000", allocations=[("savings-lot", "1")]),
    ])
    assert result.realized_profit_loss == Decimal("20000")
    assert result.positions["emergency"].remaining_cost_basis == Decimal("180000")


def test_sell_rejects_lot_from_another_source_group():
    with pytest.raises(ValueError, match="selected source group"):
        replay([
            buy("2026-01-01", quantity="1", price="80000", source="savings"),
            sell(
                "2026-02-01",
                quantity="1",
                price="100000",
                source="emergency",
                allocations=[("savings-lot", "1")],
            ),
        ])
```

- [ ] **Step 2: Run service tests and confirm RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_lot_accounting.py -v
```

Expected: import failure for `app.services.lot_accounting`.

- [ ] **Step 3: Implement minimal replay types and functions**

Provide pure helpers with these exact public signatures:

```python
@dataclass(frozen=True)
class PortfolioScope:
    kind: Literal["all", "unclassified", "source", "rollup", "label"]
    id: UUID | None = None

ValidateSellAllocations = Callable[
    [Transaction, dict[UUID, BuyLotState], Sequence[SellAllocationInput]],
    None,
]
ReplayLots = Callable[[Sequence[Transaction], PortfolioScope], ReplayResult]
BuildCurrentPositions = Callable[
    [ReplayResult, Mapping[str, Decimal | None]],
    list[ScopedHolding],
]
BuildHistory = Callable[
    [
        Sequence[Transaction],
        Mapping[str, Mapping[date, Decimal]],
        PortfolioScope,
    ],
    PortfolioHistoryOut,
]
```

Use selected buy-lot unit prices for realized P/L. Carry forward only prior
closes. Keep KRW and USD in separate series.

- [ ] **Step 4: Run service tests and confirm GREEN**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_lot_accounting.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/lot_accounting.py backend/tests/test_lot_accounting.py
git commit -m "feat: add selected lot accounting replay"
```

### Task 3: Group, Label, And Rollup Management APIs

**Files:**
- Create: `backend/app/schemas/group.py`
- Create: `backend/app/routers/groups.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_groups_api.py`

- [ ] **Step 1: Write failing API tests**

Test CRUD for source groups, rollup groups, and labels; duplicate rollup
members; rollup nesting rejection by contract; referenced-entity delete
rejection; owner isolation; UUID share-token creation; anonymous public share;
authentication-required share; and public payload ID omission.

```python
def test_rollup_group_rejects_duplicate_members(client, source_group):
    response = client.post("/api/groups/rollups", json={
        "name": "가족",
        "source_group_ids": [str(source_group.id), str(source_group.id)],
    })
    assert response.status_code == 422


def test_cross_user_cannot_update_source_group(client_for_user_b, user_a_source_group):
    response = client_for_user_b.put(
        f"/api/groups/sources/{user_a_source_group.id}",
        json={"name": "침범"},
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run API tests and confirm RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_groups_api.py -v
```

- [ ] **Step 3: Implement schemas and router**

Add `/api/groups/sources`, `/api/groups/rollups`, `/api/groups/labels`, and
`/api/groups/share/{token}` endpoints. Add `POST` and `DELETE`
`/api/groups/{kind}/{id}/share` mutations. Enforce owner checks on every
mutation. Use a shared public payload without internal IDs.

- [ ] **Step 4: Run API tests and confirm GREEN**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_groups_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/group.py backend/app/routers/groups.py backend/app/main.py backend/tests/test_groups_api.py
git commit -m "feat: add group label and rollup APIs"
```

### Task 4: Transaction Mutation And Classification APIs

**Files:**
- Modify: `backend/app/schemas/holding.py`
- Modify: `backend/app/routers/holdings.py`
- Modify: `backend/app/services/snapshot_service.py`
- Test: `backend/tests/test_holdings_lots_api.py`
- Test: `backend/tests/test_snapshot_service.py`

- [ ] **Step 1: Write failing transaction API tests**

Test initial and additional buys creating lots, unclassified buys, selected-lot
sells, lot-capacity validation, cross-owner rejection, listing available lots
by source group, classification editing, later-sell revalidation, transaction
deletion replay, soft-delete rejection for positive remaining quantity, and
history rebuild after backdated edits.

```python
def test_sell_rejects_quantity_above_selected_lot_remaining(client, holding, lot):
    response = client.post(f"/api/holdings/{holding.id}/transactions", json={
        "type": "SELL",
        "quantity": "2",
        "price": "100000",
        "transaction_date": "2026-02-01",
        "source_group_id": str(lot.source_group_id),
        "sell_allocations": [{"buy_lot_id": str(lot.id), "quantity": "2"}],
    })
    assert response.status_code == 422
```

- [ ] **Step 2: Run mutation tests and confirm RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_holdings_lots_api.py tests/test_snapshot_service.py -v
```

- [ ] **Step 3: Extend schemas and mutation endpoints**

Add:

```python
class SellLotAllocationIn(BaseModel):
    buy_lot_id: UUID
    quantity: Decimal = Field(gt=0)

class TransactionIn(BaseModel):
    type: TransactionType
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    transaction_date: date
    source_group_id: UUID | None = None
    label_ids: list[UUID] = []
    sell_allocations: list[SellLotAllocationIn] = []
```

Create buy lots on buys, validate and persist sell allocations on sells, expose
available lots, and allow classification edits. Lock the affected holding and
replay subsequent activity before flush. Rebuild derived snapshots after
backdated edits and deletes.

Expose:

```text
GET   /api/holdings/{holding_id}/lots?scope_kind=source&scope_id={source_group_id}
GET   /api/holdings/{holding_id}/lots?scope_kind=unclassified
PATCH /api/holdings/{holding_id}/transactions/{tx_id}/classification
      { "source_group_id": "uuid-or-null", "label_ids": ["label-uuid"] }
```

- [ ] **Step 4: Run mutation tests and confirm GREEN**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_holdings_lots_api.py tests/test_snapshot_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/holding.py backend/app/routers/holdings.py backend/app/services/snapshot_service.py backend/tests
git commit -m "feat: persist transaction group lots and selected sells"
```

### Task 5: Scoped Portfolio Summary, History, And Sharing

**Files:**
- Modify: `backend/app/schemas/portfolio.py`
- Modify: `backend/app/routers/portfolio.py`
- Modify: `backend/app/routers/groups.py`
- Test: `backend/tests/test_scoped_portfolio.py`

- [ ] **Step 1: Write failing scoped-query tests**

Verify source, rollup, label, unclassified, and all scopes for summary,
holdings, history, and share payloads. Check KRW/USD separation, group totals
matching the full portfolio once, carry-forward closes, and consistent inactive
holding handling.

```python
def test_rollup_scope_adds_member_sources_once():
    output = build_summary(
        scope=rollup("family", members=["savings", "emergency"]),
        positions=[
            position(ticker="005930", source="savings", quantity="1", cost_basis="80000", current_value="100000"),
            position(ticker="005930", source="emergency", quantity="2", cost_basis="180000", current_value="200000"),
        ],
    )
    assert output.currencies[Currency.KRW].total_cost_basis == Decimal("260000")
    assert output.currencies[Currency.KRW].total_current_value == Decimal("300000")
```

- [ ] **Step 2: Run scoped tests and confirm RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_scoped_portfolio.py -v
```

- [ ] **Step 3: Implement scope contracts and endpoints**

Expose:

```text
GET /api/portfolio/summary?scope_kind=&scope_id=
GET /api/portfolio/holdings?scope_kind=&scope_id=
GET /api/portfolio/history?scope_kind=&scope_id=
```

Resolve rollup members once, delegate calculation to `lot_accounting`, and use
the same scope calculation for public shares.

- [ ] **Step 4: Run scoped tests and confirm GREEN**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_scoped_portfolio.py -v
```

- [ ] **Step 5: Run backend regression suite**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/portfolio.py backend/app/routers/portfolio.py backend/app/routers/groups.py backend/tests
git commit -m "feat: add scoped lot portfolio reporting"
```

### Task 6: Transaction-Level Frontend Inputs

**Files:**
- Create: `frontend/components/groups/SourceGroupSelect.tsx`
- Create: `frontend/components/groups/LabelMultiSelect.tsx`
- Create: `frontend/components/groups/SellLotAllocationEditor.tsx`
- Create: `frontend/components/groups/TransactionClassificationEditor.tsx`
- Modify: `frontend/components/holdings/HoldingForm.tsx`
- Modify: `frontend/components/holdings/AddTransactionForm.tsx`
- Modify: `frontend/components/holdings/TransactionList.tsx`
- Modify: `frontend/app/holdings/[id]/page.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/types.ts`
- Test: `frontend/__tests__/components/HoldingForm.test.tsx`
- Create: `frontend/__tests__/components/AddTransactionForm.test.tsx`
- Create: `frontend/__tests__/components/TransactionList.test.tsx`

- [ ] **Step 1: Write failing component tests**

Test unclassified default, source selection, label multi-select, buy payload,
sell source selection, lot loading, selected allocation totals, capacity
errors, label suggestions, and classification edit payloads.

```tsx
it('submits selected buy lots for a sell', async () => {
  render(<AddTransactionForm holdingId="holding-1" onSuccess={jest.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: '매도' }))
  fireEvent.change(screen.getByLabelText('자금 출처'), { target: { value: 'source-1' } })
  fireEvent.change(screen.getByLabelText('2026-01-01 매수 lot 수량'), { target: { value: '1' } })
  fireEvent.click(screen.getByRole('button', { name: '추가' }))
  await waitFor(() => expect(holdingsApi.addTransaction).toHaveBeenCalledWith(
    'holding-1',
    expect.objectContaining({
      source_group_id: 'source-1',
      sell_allocations: [{ buy_lot_id: 'lot-1', quantity: '1' }],
    }),
  ))
})
```

- [ ] **Step 2: Run component tests and confirm RED**

Run:

```bash
cd frontend
npm test -- --runInBand __tests__/components/HoldingForm.test.tsx __tests__/components/AddTransactionForm.test.tsx __tests__/components/TransactionList.test.tsx
```

- [ ] **Step 3: Implement reusable controls and wire forms**

Replace holding-level tag post-processing with transaction payloads. Render
source group and labels on each transaction row and add classification edit.

- [ ] **Step 4: Run component tests and confirm GREEN**

Run the same Jest command and expect PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/groups frontend/components/holdings frontend/app/holdings frontend/lib frontend/__tests__
git commit -m "feat: add transaction lot classification UI"
```

### Task 7: Management, Scope Filter, Dual-Axis Chart, And Shares

**Files:**
- Create: `frontend/components/groups/GroupManager.tsx`
- Create: `frontend/components/dashboard/ScopeFilter.tsx`
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Modify: `frontend/components/dashboard/PortfolioSummary.tsx`
- Modify: `frontend/components/dashboard/HoldingsTable.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/tags/page.tsx`
- Modify: `frontend/app/share/[token]/page.tsx`
- Modify: `frontend/components/layout/Navbar.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/types.ts`
- Create: `frontend/__tests__/components/GroupManager.test.tsx`
- Create: `frontend/__tests__/components/ScopeFilter.test.tsx`
- Modify: `frontend/__tests__/dashboard/PortfolioChart.test.ts`

- [ ] **Step 1: Write failing management and dashboard tests**

Test separate source, rollup, and label sections; rollup member selection;
scope-query URL generation; one chart container with KRW left-axis and USD
right-axis series; and shared payload rendering.

```ts
it('builds dual-axis currency series without adding currencies', () => {
  const series = buildCurrencySeries({
    KRW: [{ snapshot_date: '2026-01-01', total_value: '100000', total_cost_basis: '80000' }],
    USD: [{ snapshot_date: '2026-01-01', total_value: '100', total_cost_basis: '80' }],
  })
  expect(series.KRW.priceScaleId).toBe('left')
  expect(series.USD.priceScaleId).toBe('right')
})
```

- [ ] **Step 2: Run dashboard tests and confirm RED**

Run:

```bash
cd frontend
npm test -- --runInBand __tests__/components/GroupManager.test.tsx __tests__/components/ScopeFilter.test.tsx __tests__/dashboard/PortfolioChart.test.ts
```

- [ ] **Step 3: Implement management and scoped dashboard**

Use one chart instance with currency-specific axes, no FX summation, and a
scope filter that updates summary, holdings, and history URLs together. Render
shared source, rollup, or label payloads through one shared page.

- [ ] **Step 4: Run frontend regression and production build**

Run:

```bash
cd frontend
npm test -- --runInBand
npm run build
```

Expected: PASS. Existing `AuthForm` act warnings may remain but no new warnings
should be introduced.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add scoped dashboard groups and dual-axis chart"
```

### Task 8: Deployment Verification And Legacy Review

**Files:**
- Create: `scripts/verify_group_lot_migration.py`
- Modify: `docs/v2-redesign.md`

- [ ] **Step 1: Add a migration verification script**

The read-only script reports:

```text
users / holdings / transactions
legacy holding_tags
source groups / rollups / labels
buy lots / sell allocations
unclassified lots
requires_review transactions
cross-owner relation mismatches
buy-lot remaining quantity mismatches
```

- [ ] **Step 2: Run all backend, frontend, migration, and whitespace checks**

Run:

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic check
.venv/bin/python -m pytest tests/
cd ../frontend
npm test -- --runInBand
npm run build
cd ..
backend/.venv/bin/python scripts/verify_group_lot_migration.py
git diff --check
```

- [ ] **Step 3: Restart persistent services and verify the browser flow**

Verify on `https://stock2.realchoi.com`:

1. Create `모음통장` and `긴급통장` source groups.
2. Create rollup group `가족`.
3. Register Samsung Electronics buys for one and two shares respectively.
4. Confirm `가족` shows three shares once.
5. Sell one selected buy lot.
6. Confirm overselling is rejected.
7. Confirm KRW and USD render in one chart with separate axes.
8. Confirm a shared scope link exposes no internal IDs.

- [ ] **Step 4: Update V2 documentation**

Replace the holding-level tag decision with source groups, rollup groups,
labels, buy lots, selected-lot sells, and expand/contract migration notes.

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_group_lot_migration.py docs/v2-redesign.md
git commit -m "docs: verify transaction group lot rollout"
```

## Final Review

After all tasks:

1. Dispatch a spec-compliance reviewer against
   `docs/superpowers/specs/2026-06-02-transaction-group-lot-design.md`.
2. Dispatch a code-quality and security reviewer across the complete diff.
3. Apply required fixes using RED-GREEN-REFACTOR.
4. Re-run Task 8 verification.
5. Use Superpowers `verification-before-completion` and
   `finishing-a-development-branch`.
