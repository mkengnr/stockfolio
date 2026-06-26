# 공유 페이지 종목 상세 (읽기 전용) + 거래내역 공유 옵션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공유 페이지에서 종목 상세(읽기 전용, 그룹 스코프 한정)로 이동할 수 있게 하고, 거래내역 노출 여부를 공유 옵션으로 추가한다.

**Architecture:** 백엔드는 source/rollup/label 그룹 모델에 `share_show_transactions` 플래그를 추가하고, 토큰 기반 읽기 전용 종목 상세 엔드포인트(`GET /api/groups/share/{token}/holdings/{holding_id}`)를 신설한다. 성과/그룹별 계산은 기존 `_holding_performance`를 스코프 인자를 받도록 일반화해 재사용한다. 프론트는 공유 테이블에 `holding_id`를 노출해 링크를 활성화하고, 인증 게이트 없는 신규 상세 라우트를 추가하며, 표현형 컴포넌트(성과요약/그룹별현황/가격차트)를 공유한다.

**Tech Stack:** FastAPI, SQLAlchemy 2(async), Alembic, Pydantic v2 / Next.js 14, TypeScript, SWR, Jest + Testing Library, pytest.

---

## File Structure

**Backend**
- Modify `backend/app/models/group.py` — 3개 모델에 `share_show_transactions` 컬럼.
- Create `backend/alembic/versions/<rev>_add_share_show_transactions.py` — 마이그레이션.
- Modify `backend/app/schemas/group.py` — `ShareUpdateIn`, 신규 `ShareSettingsUpdateIn`, `GroupMetadataOut`, `SharedDashboardHoldingOut`, 신규 `SharedHoldingDetailOut` / `SharedHoldingTransactionOut` / `SharedHoldingSnapshotOut` / `SharedHoldingPerformanceOut` / `SharedHoldingGroupBreakdownOut`.
- Modify `backend/app/routers/holdings.py` — `_holding_performance`에 `scope` 인자 추가.
- Modify `backend/app/services/lot_accounting.py` — `lot_matches_scope` 공개 래퍼.
- Modify `backend/app/routers/groups.py` — `enable_share` 저장값, 신규 `PATCH /share`, `_public_dashboard_holding` holding_id, 신규 `GET /share/{token}/holdings/{holding_id}`.
- Tests: `backend/tests/test_groups_api.py`, `backend/tests/test_holding_performance_scope.py`(신규), `backend/tests/test_shared_holding_detail.py`(신규).

**Frontend**
- Modify `frontend/lib/types.ts` — `SharedDashboardHolding.holding_id`, 신규 `SharedHoldingDetail` / `SharedHoldingTransaction`, `GroupMetadata`(또는 그룹 타입)에 `share_show_transactions`.
- Modify `frontend/lib/shareAdapters.ts` — `toDashboardHolding`이 `holding_id` 전달.
- Modify `frontend/lib/api.ts` — `shareApi.getHolding`, `groupsApi.enableShare`(showTransactions), `groupsApi.updateShareSettings`.
- Modify `frontend/components/dashboard/HoldingsTable.tsx` — `holdingHref` prop.
- Create `frontend/components/holdings/HoldingPerformanceSummary.tsx` — 추출(소유자/공유 공용).
- Create `frontend/components/holdings/HoldingGroupBreakdownTable.tsx` — 추출(공용).
- Modify `frontend/app/holdings/[id]/page.tsx` — 추출 컴포넌트 사용.
- Modify `frontend/components/holdings/PriceChart.tsx` — `snapshots`/`transactions` prop 타입 narrowing.
- Create `frontend/components/holdings/SharedTransactionTable.tsx` — 읽기 전용 거래 테이블.
- Create `frontend/app/share/[token]/holdings/[holdingId]/page.tsx` — 신규 라우트.
- Modify `frontend/components/groups/GroupManager.tsx` — 거래내역 공개 옵션 UI.
- Modify `frontend/app/share/[token]/page.tsx` — 테이블에 `holdingHref` 주입.
- Tests: `frontend/__tests__/components/HoldingsTable.test.tsx`, `frontend/__tests__/share/SharedHoldingDetail.test.tsx`(신규), `frontend/__tests__/components/GroupManager.share.test.tsx`(신규 또는 기존 GroupManager 테스트 확장).

---

## Task 1: DB 컬럼 + 마이그레이션 + GroupMetadataOut

**Files:**
- Modify: `backend/app/models/group.py` (SourceGroup, RollupGroup, Label)
- Modify: `backend/app/schemas/group.py:113-123` (GroupMetadataOut)
- Create: `backend/alembic/versions/<rev>_add_share_show_transactions.py`
- Test: `backend/tests/test_group_migration.py`

- [ ] **Step 1: 모델에 컬럼 추가**

`backend/app/models/group.py`의 SourceGroup, RollupGroup, Label 각각 `share_requires_auth` 줄 바로 아래에 추가:

```python
    share_show_transactions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
```

- [ ] **Step 2: GroupMetadataOut에 필드 추가**

`backend/app/schemas/group.py` `GroupMetadataOut`에 `share_requires_auth: bool` 아래 추가:

```python
    share_show_transactions: bool
```

- [ ] **Step 3: 마이그레이션 생성**

Run: `cd backend && .venv/bin/alembic revision --autogenerate -m "add share_show_transactions"`
생성된 파일에서 3개 테이블 모두 `server_default="false"`로 `add_column` 되었는지 확인. 예시:

```python
def upgrade() -> None:
    for table in ("source_groups", "rollup_groups", "labels"):
        op.add_column(table, sa.Column(
            "share_show_transactions", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ))

def downgrade() -> None:
    for table in ("source_groups", "rollup_groups", "labels"):
        op.drop_column(table, "share_show_transactions")
```

- [ ] **Step 4: 마이그레이션 적용**

Run: `cd backend && .venv/bin/alembic upgrade head`
Expected: 에러 없이 완료. `.venv/bin/alembic current` 가 새 리비전 표시.

- [ ] **Step 5: 기존 그룹 테스트 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_groups_api.py tests/test_group_migration.py -q`
Expected: PASS (GroupMetadataOut에 새 필드가 있으나 모델 default로 채워짐).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/group.py backend/app/schemas/group.py backend/alembic/versions
git commit -m "feat(share): add share_show_transactions column to group models"
```

---

## Task 2: 공유 생성 시 show_transactions 저장

**Files:**
- Modify: `backend/app/schemas/group.py` (ShareUpdateIn)
- Modify: `backend/app/routers/groups.py:479-490` (enable_share)
- Test: `backend/tests/test_groups_api.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_groups_api.py` 끝에 추가 (기존 `client`, `db`, `source` 픽스처 재사용):

```python
def test_enable_share_persists_show_transactions(client, db, source):
    response = client.post(
        f"/api/groups/sources/{source.id}/share",
        json={"requires_auth": False, "show_transactions": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["share_token"]
    assert body["share_show_transactions"] is True
    assert source.share_show_transactions is True


def test_enable_share_defaults_show_transactions_false(client, db, source):
    response = client.post(
        f"/api/groups/sources/{source.id}/share",
        json={"requires_auth": False},
    )
    assert response.status_code == 200
    assert response.json()["share_show_transactions"] is False
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_groups_api.py::test_enable_share_persists_show_transactions -q`
Expected: FAIL (현재 ShareUpdateIn은 show_transactions 미수용, enable_share 미저장).

- [ ] **Step 3: 구현**

`backend/app/schemas/group.py` `ShareUpdateIn`:

```python
class ShareUpdateIn(BaseModel):
    requires_auth: bool = True
    show_transactions: bool = False

    model_config = {"extra": "forbid"}
```

`backend/app/routers/groups.py` `enable_share` 본문:

```python
    entity = await _get_owned_entity(db, kind, entity_id, current_user.id)
    entity.share_token = str(uuid.uuid4())
    entity.share_requires_auth = body.requires_auth
    entity.share_show_transactions = body.show_transactions
    return _entity_to_out(entity)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_groups_api.py -k share -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/group.py backend/app/routers/groups.py backend/tests/test_groups_api.py
git commit -m "feat(share): accept show_transactions when enabling share"
```

---

## Task 3: PATCH 공유 옵션 in-place 변경 엔드포인트

**Files:**
- Modify: `backend/app/schemas/group.py` (신규 ShareSettingsUpdateIn)
- Modify: `backend/app/routers/groups.py` (신규 PATCH `/share`)
- Test: `backend/tests/test_groups_api.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_groups_api.py`에 추가:

```python
def test_update_share_settings_toggles_show_transactions(client, db, source):
    client.post(f"/api/groups/sources/{source.id}/share", json={"requires_auth": True})
    token_before = source.share_token

    response = client.patch(
        f"/api/groups/sources/{source.id}/share",
        json={"show_transactions": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["share_show_transactions"] is True
    assert body["share_requires_auth"] is True  # 미지정 필드는 불변
    assert body["share_token"] == token_before    # 토큰 재발급 없음


def test_update_share_settings_rejects_unshared_group(client, db, source):
    response = client.patch(
        f"/api/groups/sources/{source.id}/share",
        json={"show_transactions": True},
    )
    assert response.status_code == 409
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_groups_api.py::test_update_share_settings_toggles_show_transactions -q`
Expected: FAIL (PATCH 라우트 없음 → 405).

- [ ] **Step 3: 구현**

`backend/app/schemas/group.py`에 추가:

```python
class ShareSettingsUpdateIn(BaseModel):
    requires_auth: bool | None = None
    show_transactions: bool | None = None

    model_config = {"extra": "forbid"}
```

`backend/app/routers/groups.py`의 import에 `ShareSettingsUpdateIn` 추가, `enable_share` 다음에 라우트 추가:

```python
@router.patch("/{kind}/{entity_id}/share", response_model=GroupOut)
async def update_share_settings(
    kind: GroupKind,
    entity_id: uuid.UUID,
    body: ShareSettingsUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _get_owned_entity(db, kind, entity_id, current_user.id)
    if entity.share_token is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Share is not enabled for this group",
        )
    if "requires_auth" in body.model_fields_set and body.requires_auth is not None:
        entity.share_requires_auth = body.requires_auth
    if "show_transactions" in body.model_fields_set and body.show_transactions is not None:
        entity.share_show_transactions = body.show_transactions
    return _entity_to_out(entity)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_groups_api.py -k share -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/group.py backend/app/routers/groups.py backend/tests/test_groups_api.py
git commit -m "feat(share): add PATCH endpoint to toggle share settings in place"
```

---

## Task 4: `_holding_performance` 스코프 일반화

**Files:**
- Modify: `backend/app/services/lot_accounting.py` (공개 `lot_matches_scope`)
- Modify: `backend/app/routers/holdings.py:266-345` (`_holding_performance`)
- Test: `backend/tests/test_holding_performance_scope.py` (신규)

- [ ] **Step 1: lot_accounting 공개 래퍼 추가**

`backend/app/services/lot_accounting.py`의 `_lot_matches_scope` 정의 아래에 추가:

```python
def lot_matches_scope(lot: BuyLotState, scope: PortfolioScope) -> bool:
    """Public wrapper so routers can filter replayed lots by portfolio scope."""
    return _lot_matches_scope(lot, scope)
```

- [ ] **Step 2: 실패 테스트 작성**

`backend/tests/test_holding_performance_scope.py` 생성. 픽스처는 `tests/test_shared_dashboard_builder.py`의 holding/transaction 구성 방식을 참고하되, 단일 holding에 두 출처 그룹의 매수 lot을 만든다:

```python
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.models.holding import Currency, Market, PrincipalFlow, TransactionType
from app.routers.holdings import _holding_performance
from app.services.lot_accounting import PortfolioScope

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _tx(*, tx_id, sgid, type_, qty, price, day, lot_id=None, allocations=()):
    return SimpleNamespace(
        id=tx_id, source_group_id=sgid, type=type_,
        quantity=Decimal(qty), price=Decimal(price),
        transaction_date=date(2026, 1, day), created_at=NOW,
        principal_flow=(PrincipalFlow.DEPOSIT if type_ == TransactionType.BUY else PrincipalFlow.WITHDRAW),
        requires_review=False,
        buy_lot=SimpleNamespace(id=lot_id) if lot_id else None,
        sell_allocations=list(allocations),
        transaction_labels=[],
    )


def _holding(transactions):
    return SimpleNamespace(
        id=uuid.uuid4(), ticker="005930", currency=Currency.KRW,
        market=Market.KRX, name="삼성전자", transactions=transactions,
    )


def test_source_scope_limits_principal_and_breakdown():
    sg_a, sg_b = uuid.uuid4(), uuid.uuid4()
    lot_a, lot_b = uuid.uuid4(), uuid.uuid4()
    holding = _holding([
        _tx(tx_id=uuid.uuid4(), sgid=sg_a, type_=TransactionType.BUY, qty="10", price="100", day=1, lot_id=lot_a),
        _tx(tx_id=uuid.uuid4(), sgid=sg_b, type_=TransactionType.BUY, qty="5", price="200", day=2, lot_id=lot_b),
    ])
    sources = [
        SimpleNamespace(id=sg_a, name="A", color="#111111"),
        SimpleNamespace(id=sg_b, name="B", color="#222222"),
    ]
    perf, breakdown = _holding_performance(
        holding, Decimal("150"), sources, scope=PortfolioScope("source", sg_a)
    )
    # 스코프 A만: 원금 10*100=1000, 잔여원금 1000, 평가 10*150=1500
    assert perf.total_invested_principal == Decimal("1000")
    assert perf.remaining_cost_basis == Decimal("1000")
    assert perf.current_value == Decimal("1500")
    assert [b.source_group_id for b in breakdown] == [sg_a]


def test_all_scope_matches_legacy_default():
    sg_a = uuid.uuid4()
    lot_a = uuid.uuid4()
    holding = _holding([
        _tx(tx_id=uuid.uuid4(), sgid=sg_a, type_=TransactionType.BUY, qty="10", price="100", day=1, lot_id=lot_a),
    ])
    sources = [SimpleNamespace(id=sg_a, name="A", color="#111111")]
    perf, breakdown = _holding_performance(holding, Decimal("150"), sources)
    assert perf.total_invested_principal == Decimal("1000")
    assert len(breakdown) == 1
```

> 참고: `_to_accounting_transaction`은 `holding.ticker/currency`, `transaction.buy_lot.id`, `principal_flow` 를 사용하므로 SimpleNamespace에 해당 속성이 있어야 한다. 실패 시 필드를 기존 `test_shared_dashboard_builder.py` 픽스처와 대조해 보완.

- [ ] **Step 3: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_holding_performance_scope.py -q`
Expected: FAIL (`_holding_performance`가 `scope` kwarg 미수용).

- [ ] **Step 4: 구현**

`backend/app/routers/holdings.py` import에 `lot_matches_scope` 추가:

```python
from app.services.lot_accounting import (
    PortfolioScope,
    SellAllocationInput,
    Transaction as AccountingTransaction,
    invested_principal_by_currency,
    lot_matches_scope,
    replay,
)
```

`_holding_performance` 시그니처/본문 수정:

```python
def _holding_performance(
    holding: Holding,
    current_price: Decimal | None,
    source_groups: list[SourceGroup],
    scope: PortfolioScope = PortfolioScope("all"),
) -> tuple[HoldingPerformanceOut | None, list[HoldingGroupBreakdownOut]]:
    transactions = [_to_accounting_transaction(holding, transaction) for transaction in holding.transactions]
    replay_result = replay(transactions)
    if replay_result.accounting_status == "requires_review":
        return None, []
    invested_principal = _scope_invested_principal(transactions, holding, scope)
    scoped_lots = [lot for lot in replay_result.lots.values() if lot_matches_scope(lot, scope)]
    remaining_cost_basis = sum(
        (lot.remaining_quantity * lot.unit_price for lot in scoped_lots),
        ZERO,
    )
    remaining_quantity = sum(
        (lot.remaining_quantity for lot in scoped_lots),
        ZERO,
    )
    current_value = remaining_quantity * current_price if current_price is not None else None
    profit_loss = current_value - remaining_cost_basis if current_value is not None else None
    performance = HoldingPerformanceOut(
        total_invested_principal=invested_principal,
        remaining_cost_basis=remaining_cost_basis,
        current_value=current_value,
        profit_loss=profit_loss,
        profit_loss_pct=_profit_loss_pct(profit_loss, remaining_cost_basis),
    )

    source_by_id = {source_group.id: source_group for source_group in source_groups}
    lot_totals: dict[uuid.UUID | None, tuple[Decimal, Decimal]] = {}
    for lot in scoped_lots:
        if lot.remaining_quantity <= ZERO:
            continue
        quantity, cost_basis = lot_totals.get(lot.source_group_id, (ZERO, ZERO))
        lot_totals[lot.source_group_id] = (
            quantity + lot.remaining_quantity,
            cost_basis + lot.remaining_quantity * lot.unit_price,
        )
```

(이후 `group_breakdown` 루프는 기존 코드 그대로 — `lot_totals` 기준으로 동작하므로 변경 불필요. 단, 각 그룹의 `group_invested_principal` 계산에 쓰는 내부 `scope` 지역변수가 함수 인자 `scope`를 가린다. 내부 루프 변수명을 `group_scope`로 변경:)

```python
    group_breakdown: list[HoldingGroupBreakdownOut] = []
    for source_group_id, (remaining_quantity, group_cost_basis) in sorted(
        lot_totals.items(),
        key=lambda item: (
            item[0] is None,
            source_by_id[item[0]].name if item[0] in source_by_id else "미분류",
            str(item[0]),
        ),
    ):
        source_group = source_by_id.get(source_group_id) if source_group_id is not None else None
        group_scope = (
            PortfolioScope("source", source_group_id)
            if source_group_id is not None
            else PortfolioScope("unclassified")
        )
        group_invested_principal = _scope_invested_principal(transactions, holding, group_scope)
        group_current_value = (
            remaining_quantity * current_price if current_price is not None else None
        )
        group_profit_loss = (
            group_current_value - group_cost_basis
            if group_current_value is not None
            else None
        )
        group_breakdown.append(
            HoldingGroupBreakdownOut(
                source_group_id=source_group_id,
                name=source_group.name if source_group is not None else "미분류",
                color=source_group.color if source_group is not None else None,
                remaining_quantity=remaining_quantity,
                invested_principal=group_invested_principal,
                remaining_cost_basis=group_cost_basis,
                current_value=group_current_value,
                profit_loss=group_profit_loss,
                profit_loss_pct=_profit_loss_pct(group_profit_loss, group_cost_basis),
            )
        )
    return performance, group_breakdown
```

- [ ] **Step 5: 통과 + 회귀 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_holding_performance_scope.py tests/test_holdings_lots_api.py -q`
Expected: PASS (기존 get_holding 경로는 기본 scope=all 로 동일 동작).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/lot_accounting.py backend/app/routers/holdings.py backend/tests/test_holding_performance_scope.py
git commit -m "feat(holdings): make _holding_performance scope-aware"
```

---

## Task 5: 공유 종목 스키마 + dashboard holding_id 노출

**Files:**
- Modify: `backend/app/schemas/group.py` (SharedDashboardHoldingOut + 신규 detail 스키마)
- Modify: `backend/app/routers/groups.py:141-162` (`_public_dashboard_holding`)
- Test: `backend/tests/test_shared_dashboard_builder.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_shared_dashboard_builder.py`에 추가 (기존 `_public_shared_dashboard` 호출 테스트 패턴 재사용). 기존 테스트가 만든 dashboard 객체의 holding에 `holding_id`가 있으므로, 직렬화 결과에 노출되는지 확인:

```python
def test_public_holding_exposes_holding_id():
    # 기존 테스트의 dashboard fixture 구성 헬퍼를 재사용해 dashboard 생성 후:
    shared = _public_shared_dashboard(dashboard)
    assert all(h.holding_id is not None for h in shared.holdings if h.ticker)
```

> 기존 파일에 dashboard fixture를 만드는 헬퍼/테스트가 있으면 그 값을 재사용. 없으면 가장 가까운 기존 테스트를 복제해 작성.

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_shared_dashboard_builder.py::test_public_holding_exposes_holding_id -q`
Expected: FAIL (`SharedDashboardHoldingOut`에 holding_id 없음).

- [ ] **Step 3: 스키마 구현**

`backend/app/schemas/group.py` `SharedDashboardHoldingOut`에 필드 추가(맨 위):

```python
class SharedDashboardHoldingOut(BaseModel):
    holding_id: uuid.UUID | None = None
    ticker: str
    name: str | None
    market: Market
    currency: Currency
    quantity: Decimal
    remaining_cost_basis: Decimal | None
    current_price: Decimal | None
    current_value: Decimal | None
    current_value_change: Decimal | None = None
    unrealized_profit_loss: Decimal | None
    groups: list[SharedDashboardHoldingGroupBadgeOut]
```

같은 파일 끝(`SharedDashboardOut` 뒤)에 상세 스키마 추가:

```python
class SharedHoldingTransactionOut(BaseModel):
    type: Literal["BUY", "SELL"]
    transaction_date: date
    quantity: Decimal
    price: Decimal


class SharedHoldingSnapshotOut(BaseModel):
    snapshot_date: date
    close_price: Decimal


class SharedHoldingPerformanceOut(BaseModel):
    total_invested_principal: Decimal
    remaining_cost_basis: Decimal
    current_value: Decimal | None
    profit_loss: Decimal | None
    profit_loss_pct: Decimal | None


class SharedHoldingGroupBreakdownOut(BaseModel):
    name: str
    color: str | None
    remaining_quantity: Decimal
    invested_principal: Decimal
    remaining_cost_basis: Decimal
    current_value: Decimal | None
    profit_loss: Decimal | None
    profit_loss_pct: Decimal | None


class SharedHoldingDetailOut(BaseModel):
    ticker: str
    name: str
    market: Market
    currency: Currency
    remaining_quantity: Decimal
    current_price: Decimal | None
    show_transactions: bool
    performance: SharedHoldingPerformanceOut | None
    group_breakdown: list[SharedHoldingGroupBreakdownOut]
    snapshots: list[SharedHoldingSnapshotOut]
    transactions: list[SharedHoldingTransactionOut]
```

- [ ] **Step 4: `_public_dashboard_holding`에 holding_id 전달**

`backend/app/routers/groups.py` `_public_dashboard_holding` 반환문 맨 위에 추가:

```python
    return SharedDashboardHoldingOut(
        holding_id=getattr(holding, "holding_id", None),
        ticker=holding.ticker,
        ...
    )
```

> dashboard holding 객체의 식별자 속성명을 확인(`holding_id`). `build_shared_portfolio_dashboard`가 만드는 holding 항목의 속성명과 일치시킬 것. 다르면 그 이름을 사용.

- [ ] **Step 5: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_shared_dashboard_builder.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/group.py backend/app/routers/groups.py backend/tests/test_shared_dashboard_builder.py
git commit -m "feat(share): expose holding_id and add shared holding detail schemas"
```

---

## Task 6: 공유 종목 상세 엔드포인트 (GET)

**Files:**
- Modify: `backend/app/routers/groups.py` (신규 GET + 헬퍼)
- Test: `backend/tests/test_shared_holding_detail.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_shared_holding_detail.py` 생성. `test_shared_dashboard_builder.py`의 데이터 로딩/시세 패치 패턴을 재사용해 단일 사용자·source 그룹·holding을 구성하고, source group에 `share_token`/`share_requires_auth=False`/`share_show_transactions` 설정. 핵심 케이스:

```python
# 의사코드 — 픽스처는 test_shared_dashboard_builder.py 패턴 mirror
def test_returns_scoped_detail_for_in_scope_holding(client, ...):
    # source group 공유(show_transactions=False) + holding 2 lots(sg_a, sg_b)
    resp = client.get(f"/api/groups/share/{token}/holdings/{holding_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["show_transactions"] is False
    assert body["transactions"] == []
    assert all(g["name"] == "A" for g in body["group_breakdown"])  # 스코프 내 그룹만

def test_includes_transactions_when_option_on(client, ...):
    # share_show_transactions=True
    resp = client.get(f"/api/groups/share/{token}/holdings/{holding_id}")
    assert resp.json()["show_transactions"] is True
    assert len(resp.json()["transactions"]) >= 1
    # 스코프 밖 출처의 거래는 제외됨

def test_404_for_out_of_scope_holding(client, ...):
    # 스코프(sg_a)에 lot이 전혀 없는 다른 holding
    assert client.get(f"/api/groups/share/{token}/holdings/{other_id}").status_code == 404

def test_401_when_requires_auth_and_anonymous(client, ...):
    # share_requires_auth=True, 비로그인
    assert client.get(f"/api/groups/share/{token}/holdings/{holding_id}").status_code == 401
```

> API 레벨 픽스처가 무거우면, 우선 `test_groups_api.py`의 FakeSession 패턴으로 인증 게이트(401)와 404를 검증하고, 스코프/거래내역 정확성은 `test_shared_dashboard_builder.py`의 실데이터 패턴으로 별도 검증한다.

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_shared_holding_detail.py -q`
Expected: FAIL (엔드포인트 없음 → 404 라우트 미존재/405).

- [ ] **Step 3: 구현**

`backend/app/routers/groups.py` import에 추가:

```python
from decimal import Decimal
from sqlalchemy.orm import selectinload
from app.models.holding import Holding, Transaction, TransactionType
from app.routers.holdings import _holding_load_options, _holding_performance, _load_holding_source_groups
from app.services.lot_accounting import lot_matches_scope, replay
from app.services.price_cache import get_price
from app.schemas.group import (
    SharedHoldingDetailOut,
    SharedHoldingGroupBreakdownOut,
    SharedHoldingPerformanceOut,
    SharedHoldingSnapshotOut,
    SharedHoldingTransactionOut,
)
```

`get_shared_group` 아래에 헬퍼 + 라우트 추가:

```python
def _shared_holding_in_scope(holding, scope) -> bool:
    """holding이 스코프 내에 재생된 lot을 갖는지 검사(스코프 밖 종목 누출 방지)."""
    from app.routers.holdings import _to_accounting_transaction
    replay_result = replay([_to_accounting_transaction(holding, t) for t in holding.transactions])
    return any(lot_matches_scope(lot, scope) for lot in replay_result.lots.values())


def _scoped_shared_transactions(holding, scope) -> list[SharedHoldingTransactionOut]:
    out = []
    for tx in sorted(holding.transactions, key=lambda t: (t.transaction_date, str(t.id))):
        in_scope = (
            scope.kind == "all"
            or (scope.kind == "source" and tx.source_group_id == scope.id)
            or (scope.kind == "unclassified" and tx.source_group_id is None)
            or (scope.kind == "rollup" and tx.source_group_id in scope.resolved_source_group_ids)
            or (scope.kind == "label" and scope.id in {tl.label_id for tl in tx.transaction_labels})
        )
        if not in_scope:
            continue
        out.append(SharedHoldingTransactionOut(
            type=tx.type.value if hasattr(tx.type, "value") else tx.type,
            transaction_date=tx.transaction_date,
            quantity=tx.quantity,
            price=tx.price,
        ))
    return out


@router.get("/share/{token}/holdings/{holding_id}", response_model=SharedHoldingDetailOut)
async def get_shared_holding_detail(
    token: uuid.UUID,
    holding_id: uuid.UUID,
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    entity = None
    public_kind = None
    for model, kind in ((SourceGroup, "source"), (RollupGroup, "rollup"), (Label, "label")):
        result = await db.execute(select(model).where(model.share_token == str(token)))
        entity = result.scalar_one_or_none()
        if entity is not None:
            public_kind = kind
            break
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    if entity.share_requires_auth and current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    scope = await resolve_portfolio_scope(db, entity.user_id, public_kind, entity.id)

    result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id)
        .where(Holding.user_id == entity.user_id)
        .options(*_holding_load_options(), selectinload(Holding.snapshots))
    )
    holding = result.scalar_one_or_none()
    if holding is None or not holding.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    if not _shared_holding_in_scope(holding, scope):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")

    try:
        price_result = await get_price(holding.ticker)
        current_price = price_result.price
    except Exception:
        current_price = None

    source_groups = await _load_holding_source_groups(db, entity.user_id, holding)
    performance, group_breakdown = _holding_performance(holding, current_price, source_groups, scope)
    # 보유수량 = 스코프 내 그룹별 잔여수량 합
    remaining_quantity = sum((b.remaining_quantity for b in group_breakdown), Decimal(0))

    return SharedHoldingDetailOut(
        ticker=holding.ticker,
        name=holding.name,
        market=holding.market,
        currency=holding.currency,
        remaining_quantity=remaining_quantity,
        current_price=current_price,
        show_transactions=entity.share_show_transactions,
        performance=(
            SharedHoldingPerformanceOut(**performance.model_dump()) if performance else None
        ),
        group_breakdown=[
            SharedHoldingGroupBreakdownOut(
                name=b.name, color=b.color, remaining_quantity=b.remaining_quantity,
                invested_principal=b.invested_principal, remaining_cost_basis=b.remaining_cost_basis,
                current_value=b.current_value, profit_loss=b.profit_loss, profit_loss_pct=b.profit_loss_pct,
            )
            for b in group_breakdown
        ],
        snapshots=[
            SharedHoldingSnapshotOut(snapshot_date=s.snapshot_date, close_price=s.close_price)
            for s in sorted(holding.snapshots, key=lambda x: x.snapshot_date)
        ],
        transactions=(
            _scoped_shared_transactions(holding, scope)
            if entity.share_show_transactions else []
        ),
    )
```

> 순환 import 주의: `groups.py`가 `holdings.py`의 헬퍼를 import. `holdings.py`는 `routers.groups`를 import하지 않으므로 안전. 실행 시 ImportError가 나면 `_to_accounting_transaction` 등을 함수 내부 지연 import로 둔다(위 헬퍼에서 이미 적용).

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_shared_holding_detail.py -q`
Expected: PASS.

- [ ] **Step 5: 전체 백엔드 회귀**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/groups.py backend/tests/test_shared_holding_detail.py
git commit -m "feat(share): add read-only scoped shared holding detail endpoint"
```

---

## Task 7: 프론트 타입 + 어댑터 + HoldingsTable 링크 prop

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/shareAdapters.ts`
- Modify: `frontend/components/dashboard/HoldingsTable.tsx`
- Modify: `frontend/app/share/[token]/page.tsx`
- Test: `frontend/__tests__/components/HoldingsTable.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

`frontend/__tests__/components/HoldingsTable.test.tsx`에 추가 (기존 렌더 헬퍼 재사용):

```tsx
it('uses custom holdingHref when provided', () => {
  const holdings = [{
    holding_id: 'abc', ticker: '005930', name: '삼성전자', market: 'KRX', currency: 'KRW',
    quantity: '10', remaining_cost_basis: '1000', current_price: '150',
    current_value: '1500', unrealized_profit_loss: '500', groups: [],
  }]
  render(<HoldingsTable holdings={holdings as any} holdingHref={(id) => `/share/T/holdings/${id}`} />)
  expect(screen.getByText('삼성전자').closest('a')).toHaveAttribute('href', '/share/T/holdings/abc')
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm test -- HoldingsTable`
Expected: FAIL (holdingHref prop 없음).

- [ ] **Step 3: 타입 구현**

`frontend/lib/types.ts` `SharedDashboardHolding`에 `holding_id` 추가(맨 위 필드):

```ts
export interface SharedDashboardHolding {
  holding_id: string | null
  ticker: string
  ...
}
```

같은 파일에 추가:

```ts
export interface SharedHoldingTransaction {
  type: TxType
  transaction_date: string
  quantity: string
  price: string
}

export interface SharedHoldingDetail {
  ticker: string
  name: string
  market: Market
  currency: Currency
  remaining_quantity: string
  current_price: string | null
  show_transactions: boolean
  performance: HoldingPerformance | null
  group_breakdown: HoldingGroupBreakdown[]
  snapshots: { snapshot_date: string; close_price: string }[]
  transactions: SharedHoldingTransaction[]
}
```

그룹 타입(SourceGroup/RollupGroup/Label의 공통 메타)에서 공유 상태 표시를 위해 `share_show_transactions: boolean` 추가. (해당 인터페이스 위치 확인 후 추가; `share_requires_auth` 옆.)

- [ ] **Step 4: 어댑터 구현**

`frontend/lib/shareAdapters.ts` `toDashboardHolding`:

```ts
  return {
    holding_id: holding.holding_id,
    ticker: holding.ticker,
    ...
```

- [ ] **Step 5: HoldingsTable prop 구현**

`frontend/components/dashboard/HoldingsTable.tsx`:

```tsx
interface Props {
  holdings: TableHolding[]
  displayCurrency?: DisplayCurrency
  stickyTop?: number
  holdingHref?: (id: string) => string
}

export function HoldingsTable({ holdings, displayCurrency, stickyTop, holdingHref }: Props) {
```

`HoldingName` 호출부와 정의를 href 받도록 변경:

```tsx
{row.id ? <HoldingName row={row} href={(holdingHref ?? defaultHoldingHref)(row.id)} /> : <HoldingName row={row} />}
```

파일 상단에 `const defaultHoldingHref = (id: string) => \`/holdings/${id}\`` 추가. `HoldingName`:

```tsx
function HoldingName({ row, href }: { row: Row; href?: string }) {
  const content = (<>
      <span className="truncate font-medium text-gray-900 group-hover:text-brand-600">{row.name}</span>
      <span className="truncate text-xs text-gray-400">{row.subtitle}</span>
  </>)
  return href
    ? <Link href={href} className="group flex min-w-0 max-w-full flex-col">{content}</Link>
    : <div className="flex min-w-0 max-w-full flex-col">{content}</div>
}
```

- [ ] **Step 6: 공유 페이지에서 주입**

`frontend/app/share/[token]/page.tsx` — `SharedGroupView`에 `token: string` prop 추가, `SharePage`에서 `token={params.token}` 전달, 보유 종목 `HoldingsTable`에 prop 추가:

```tsx
<HoldingsTable
  holdings={selectedHoldings}
  displayCurrency={group.dashboard.display_currency}
  stickyTop={shareHoldingsTableStickyTop}
  holdingHref={(id) => `/share/${token}/holdings/${id}`}
/>
```

- [ ] **Step 7: 통과 확인**

Run: `cd frontend && npm test -- HoldingsTable && npx tsc --noEmit`
Expected: PASS, 타입 에러 없음.

- [ ] **Step 8: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/shareAdapters.ts frontend/components/dashboard/HoldingsTable.tsx frontend/app/share/[token]/page.tsx frontend/__tests__/components/HoldingsTable.test.tsx
git commit -m "feat(share): link shared holdings table rows to shared detail"
```

---

## Task 8: 표현형 컴포넌트 추출 + PriceChart 타입 narrowing

**Files:**
- Create: `frontend/components/holdings/HoldingPerformanceSummary.tsx`
- Create: `frontend/components/holdings/HoldingGroupBreakdownTable.tsx`
- Modify: `frontend/app/holdings/[id]/page.tsx`
- Modify: `frontend/components/holdings/PriceChart.tsx`
- Test: `frontend/__tests__/holdings/HoldingPage.test.tsx` (회귀)

- [ ] **Step 1: 성과요약 컴포넌트 추출**

`frontend/components/holdings/HoldingPerformanceSummary.tsx` 생성 — 현재 `app/holdings/[id]/page.tsx`의 `HoldingPerformanceSummary`와 `formatLastUpdated` 외 본문을 옮기되, `holding` 대신 `performance`/`quantity`/`currency`를 받도록 변경:

```tsx
import { Card } from '@/components/ui/Card'
import { formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { Currency, HoldingPerformance } from '@/lib/types'

export function HoldingPerformanceSummary({
  performance, quantity, currency,
}: { performance: HoldingPerformance | null; quantity: string; currency: Currency }) {
  const cards = [
    { label: '보유수량', value: `${parseFloat(quantity).toLocaleString()}주` },
    { label: '투자원금', value: performance ? formatCurrency(performance.total_invested_principal, currency) : '—' },
    { label: '잔여원금', value: performance ? formatCurrency(performance.remaining_cost_basis, currency) : '—' },
    { label: '평가금액', value: performance?.current_value ? formatCurrency(performance.current_value, currency) : '—' },
    { label: '손익', value: performance?.profit_loss ? formatCurrency(performance.profit_loss, currency) : '—', colorClass: profitColor(performance?.profit_loss ?? null) },
    { label: '손익률', value: formatPercent(performance?.profit_loss_pct ?? null), colorClass: profitColor(performance?.profit_loss_pct ?? null) },
  ]
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {cards.map(({ label, value, colorClass }) => (
        <Card key={label}>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</p>
          <p className={`mt-1 text-lg font-bold tabular-nums ${colorClass ?? 'text-gray-900'}`}>{value}</p>
        </Card>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: 그룹별현황 컴포넌트 추출**

`frontend/components/holdings/HoldingGroupBreakdownTable.tsx` 생성 — 현재 page.tsx의 `HoldingGroupBreakdownTable` 본문을 옮기되 `group_breakdown`/`currency`를 직접 받도록:

```tsx
import { Card } from '@/components/ui/Card'
import { formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { Currency, HoldingGroupBreakdown } from '@/lib/types'

export function HoldingGroupBreakdownTable({
  groupBreakdown, currency,
}: { groupBreakdown: HoldingGroupBreakdown[]; currency: Currency }) {
  if (groupBreakdown.length === 0) {
    return (
      <Card>
        <h2 className="font-semibold text-gray-900">그룹별 수익현황</h2>
        <p className="mt-2 text-sm text-gray-500">현재 보유 중인 그룹별 잔여 수량이 없습니다.</p>
      </Card>
    )
  }
  return (
    <Card>
      <h2 className="mb-4 font-semibold text-gray-900">그룹별 수익현황</h2>
      <div className="overflow-x-auto">
        {/* 기존 page.tsx의 table 마크업 그대로, holding.group_breakdown → groupBreakdown, holding.currency → currency */}
      </div>
    </Card>
  )
}
```

> 기존 `app/holdings/[id]/page.tsx`의 `<table>...</table>` 전체를 복사해 넣고 `holding.group_breakdown` → `groupBreakdown`, `holding.currency` → `currency`로 치환.

- [ ] **Step 3: 소유자 페이지에서 추출 컴포넌트 사용**

`frontend/app/holdings/[id]/page.tsx`에서 로컬 `HoldingPerformanceSummary`/`HoldingGroupBreakdownTable` 정의 삭제, import로 교체, 호출부 수정:

```tsx
import { HoldingPerformanceSummary } from '@/components/holdings/HoldingPerformanceSummary'
import { HoldingGroupBreakdownTable } from '@/components/holdings/HoldingGroupBreakdownTable'
...
<HoldingPerformanceSummary performance={holding.performance} quantity={holding.quantity} currency={holding.currency} />
...
<HoldingGroupBreakdownTable groupBreakdown={holding.group_breakdown} currency={holding.currency} />
```

- [ ] **Step 4: PriceChart 타입 narrowing**

`frontend/components/holdings/PriceChart.tsx` Props 변경(사용 필드만):

```tsx
interface Props {
  snapshots: { snapshot_date: string; close_price: string }[]
  currency: 'KRW' | 'USD'
  currentPrice: string | null
  transactions: { transaction_date: string; type: TxType; quantity: string }[]
}
```

`import type { Snapshot, Transaction }` → `import type { TxType }`로 정리(`buildPricePoints`/`buildTransactionMarkers` 시그니처도 동일 narrowing). 기존 호출(소유자 페이지)은 전체 `Snapshot[]`/`Transaction[]`가 구조적으로 호환되어 변경 불필요.

- [ ] **Step 5: 회귀 확인**

Run: `cd frontend && npm test -- HoldingPage PriceChart && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/holdings/HoldingPerformanceSummary.tsx frontend/components/holdings/HoldingGroupBreakdownTable.tsx frontend/app/holdings/[id]/page.tsx frontend/components/holdings/PriceChart.tsx
git commit -m "refactor(holdings): extract performance/breakdown components, narrow PriceChart props"
```

---

## Task 9: 공유 종목 상세 라우트 + 읽기 전용 거래 테이블

**Files:**
- Modify: `frontend/lib/api.ts` (shareApi.getHolding)
- Create: `frontend/components/holdings/SharedTransactionTable.tsx`
- Create: `frontend/app/share/[token]/holdings/[holdingId]/page.tsx`
- Test: `frontend/__tests__/share/SharedHoldingDetail.test.tsx` (신규)

- [ ] **Step 1: API 추가**

`frontend/lib/api.ts` `shareApi`에 추가(`SharedHoldingDetail` import):

```ts
export const shareApi = {
  getGroup: (token: string) => request<SharedGroup>(`/api/groups/share/${token}`),
  getLegacy: (token: string) => request<SharedTag>(`/api/share/${token}`),
  getHolding: (token: string, holdingId: string) =>
    request<SharedHoldingDetail>(`/api/groups/share/${token}/holdings/${holdingId}`),
}
```

- [ ] **Step 2: 읽기 전용 거래 테이블 컴포넌트**

`frontend/components/holdings/SharedTransactionTable.tsx` 생성:

```tsx
import { formatCurrency, formatDate, formatNumber } from '@/lib/utils'
import { Badge } from '@/components/ui/Badge'
import type { Currency, SharedHoldingTransaction } from '@/lib/types'

export function SharedTransactionTable({
  transactions, currency,
}: { transactions: SharedHoldingTransaction[]; currency: Currency }) {
  if (transactions.length === 0) {
    return <p className="text-sm text-gray-400">거래 내역이 없습니다.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
            <th className="px-3 py-2">구분</th>
            <th className="px-3 py-2">날짜</th>
            <th className="px-3 py-2 text-right">수량</th>
            <th className="px-3 py-2 text-right">단가</th>
            <th className="px-3 py-2 text-right">금액</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {transactions.map((tx, i) => (
            <tr key={i}>
              <td className="px-3 py-2"><Badge color={tx.type === 'BUY' ? '#16a34a' : '#dc2626'}>{tx.type === 'BUY' ? '매수' : '매도'}</Badge></td>
              <td className="px-3 py-2 text-gray-700">{formatDate(tx.transaction_date)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-gray-700">{formatNumber(parseFloat(tx.quantity), 0)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-gray-700">{formatCurrency(tx.price, currency)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-gray-700">{formatCurrency(parseFloat(tx.quantity) * parseFloat(tx.price), currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

> `Badge`가 임의 hex color를 받는지 확인(기존 사용처에서 그룹 color 사용 → OK). 아니면 색 클래스 텍스트로 대체.

- [ ] **Step 3: 실패 테스트 작성**

`frontend/__tests__/share/SharedHoldingDetail.test.tsx` 생성 (`__tests__/share/SharePage.test.tsx`의 mock 패턴 재사용 — `shareApi` mock):

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import SharedHoldingPage from '@/app/share/[token]/holdings/[holdingId]/page'
import { shareApi } from '@/lib/api'

jest.mock('@/lib/api')
jest.mock('@/components/holdings/PriceChart', () => ({ PriceChart: () => <div data-testid="price-chart" /> }))

const base = {
  ticker: '005930', name: '삼성전자', market: 'KRX', currency: 'KRW',
  remaining_quantity: '10', current_price: '150',
  performance: null, group_breakdown: [], snapshots: [],
}

it('renders read-only detail without delete or add-transaction controls', async () => {
  ;(shareApi.getHolding as jest.Mock).mockResolvedValue({ ...base, show_transactions: false, transactions: [] })
  render(<SharedHoldingPage params={{ token: 'T', holdingId: 'H' }} />)
  await screen.findByText('삼성전자')
  expect(screen.queryByText('종목 삭제')).toBeNull()
  expect(screen.queryByText('거래 추가')).toBeNull()
  expect(screen.queryByText('거래 내역')).toBeNull()  // 옵션 OFF → 섹션 없음
})

it('shows transactions section when show_transactions is true', async () => {
  ;(shareApi.getHolding as jest.Mock).mockResolvedValue({
    ...base, show_transactions: true,
    transactions: [{ type: 'BUY', transaction_date: '2026-01-01', quantity: '10', price: '100' }],
  })
  render(<SharedHoldingPage params={{ token: 'T', holdingId: 'H' }} />)
  await screen.findByText('거래 내역')
  expect(screen.getByText('매수')).toBeInTheDocument()
})
```

- [ ] **Step 4: 실패 확인**

Run: `cd frontend && npm test -- SharedHoldingDetail`
Expected: FAIL (페이지 없음).

- [ ] **Step 5: 라우트 구현**

`frontend/app/share/[token]/holdings/[holdingId]/page.tsx` 생성:

```tsx
'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { PriceChart } from '@/components/holdings/PriceChart'
import { HoldingPerformanceSummary } from '@/components/holdings/HoldingPerformanceSummary'
import { HoldingGroupBreakdownTable } from '@/components/holdings/HoldingGroupBreakdownTable'
import { SharedTransactionTable } from '@/components/holdings/SharedTransactionTable'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { shareApi } from '@/lib/api'
import type { SharedHoldingDetail } from '@/lib/types'

export default function SharedHoldingPage({ params }: { params: { token: string; holdingId: string } }) {
  const [holding, setHolding] = useState<SharedHoldingDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [loginRequired, setLoginRequired] = useState(false)

  const load = useCallback(async (initial = false) => {
    if (initial) setLoading(true); else setRefreshing(true)
    setError(''); setLoginRequired(false)
    try {
      setHolding(await shareApi.getHolding(params.token, params.holdingId))
    } catch (err) {
      const statusCode = (err as Error & { status?: number }).status
      if (statusCode === 401) { setError('로그인이 필요한 공유 링크입니다.'); setLoginRequired(true) }
      else if (statusCode === 404) setError('종목을 찾을 수 없습니다.')
      else setError('종목 정보를 불러오지 못했습니다.')
    } finally {
      if (initial) setLoading(false); else setRefreshing(false)
    }
  }, [params.token, params.holdingId])

  useEffect(() => { void load(true) }, [load])

  if (loading) return <PageLoader />
  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3">
        <p className="text-gray-500">{error}</p>
        {loginRequired && (
          <Link href={`/auth?returnTo=${encodeURIComponent(`/share/${params.token}/holdings/${params.holdingId}`)}`}
            className="text-sm font-medium text-brand-600 hover:text-brand-700">로그인</Link>
        )}
      </div>
    )
  }
  if (!holding) return null

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <Link href={`/share/${params.token}`} className="text-sm text-gray-400 hover:text-gray-600">공유 포트폴리오</Link>
          <span className="text-gray-300">/</span>
          <span className="text-sm text-gray-600">{holding.name}</span>
        </div>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="mt-1 text-xl font-semibold text-gray-900">{holding.name}</h1>
            <p className="text-sm text-gray-400">{holding.ticker} · {holding.market} · {holding.currency}</p>
          </div>
          <Button variant="secondary" size="sm" loading={refreshing} onClick={() => void load(false)}>새로고침</Button>
        </div>
      </div>

      <HoldingPerformanceSummary performance={holding.performance} quantity={holding.remaining_quantity} currency={holding.currency} />

      <Card>
        <h2 className="mb-4 font-semibold text-gray-900">가격 차트</h2>
        <PriceChart snapshots={holding.snapshots} currency={holding.currency} currentPrice={holding.current_price} transactions={holding.transactions} />
      </Card>

      <HoldingGroupBreakdownTable groupBreakdown={holding.group_breakdown} currency={holding.currency} />

      {holding.show_transactions && (
        <Card>
          <h2 className="mb-4 font-semibold text-gray-900">거래 내역</h2>
          <SharedTransactionTable transactions={holding.transactions} currency={holding.currency} />
        </Card>
      )}
      <p className="mt-8 text-center text-xs text-gray-300">powered by realchoi</p>
    </div>
  )
}
```

> 보유수량 표시: 공유 상세에는 별도 수량 필드가 없다. `HoldingPerformanceSummary`의 `quantity`는 그룹별현황 합으로 구하거나, 백엔드 `SharedHoldingDetailOut`에 `remaining_quantity: Decimal`를 추가해 전달하는 편이 정확하다. **구현 시 백엔드 스키마에 `remaining_quantity` 추가(Task 5/6 보강)** 후 `quantity={holding.remaining_quantity}` 로 연결. (계획 자기검토에서 보강 항목으로 명시.)

- [ ] **Step 6: 통과 확인**

Run: `cd frontend && npm test -- SharedHoldingDetail && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/api.ts frontend/components/holdings/SharedTransactionTable.tsx "frontend/app/share/[token]/holdings/[holdingId]/page.tsx" frontend/__tests__/share/SharedHoldingDetail.test.tsx
git commit -m "feat(share): add read-only shared holding detail page"
```

---

## Task 10: GroupManager 거래내역 공개 옵션 UI

**Files:**
- Modify: `frontend/lib/api.ts` (groupsApi.enableShare, updateShareSettings)
- Modify: `frontend/components/groups/GroupManager.tsx`
- Test: `frontend/__tests__/components/GroupManager.share.test.tsx` (신규)

- [ ] **Step 1: API 구현**

`frontend/lib/api.ts` `groupsApi`:

```ts
  enableShare: (kind: GroupKind, id: string, requiresAuth: boolean, showTransactions = false) =>
    request(`/api/groups/${kind}/${id}/share`, {
      method: 'POST',
      body: JSON.stringify({ requires_auth: requiresAuth, show_transactions: showTransactions }),
    }),
  updateShareSettings: (kind: GroupKind, id: string, body: { requires_auth?: boolean; show_transactions?: boolean }) =>
    request(`/api/groups/${kind}/${id}/share`, { method: 'PATCH', body: JSON.stringify(body) }),
```

(기존 `enableShare` 호출부 시그니처 변경 영향 점검 — GroupManager만 사용.)

- [ ] **Step 2: 실패 테스트 작성**

`frontend/__tests__/components/GroupManager.share.test.tsx` 생성 (기존 GroupManager 테스트의 SWR/mock 패턴 재사용). 공유 활성 그룹 카드에서 "거래내역 공개" 토글이 `updateShareSettings`를 호출하는지 검증:

```tsx
// 의사코드: source 그룹 1개(share_token 존재, share_show_transactions=false) mock
// "거래내역 공개" 체크박스를 클릭 → groupsApi.updateShareSettings 가
// (kind='sources', id, { show_transactions: true }) 로 호출됨을 expect
```

- [ ] **Step 3: 실패 확인**

Run: `cd frontend && npm test -- GroupManager.share`
Expected: FAIL.

- [ ] **Step 4: UI 구현**

`GroupManager.tsx` 미공유 카드 폼에 체크박스 추가(상태 `showTransactions`):

```tsx
<label className="flex items-center gap-2 text-xs text-gray-600">
  <input type="checkbox" checked={showTransactions} onChange={(e) => setShowTransactions(e.target.checked)} />
  거래내역 공개
</label>
```

`onEnableShare(kind, group, requiresAuth, showTransactions)` 로 전달(시그니처 확장). 공유 활성 카드에는 토글 추가:

```tsx
<label className="mt-2 flex items-center gap-2 text-xs text-gray-600">
  <input
    type="checkbox"
    checked={group.share_show_transactions}
    onChange={(e) => onUpdateShareSettings(kind, group, { show_transactions: e.target.checked })}
  />
  거래내역 공개
</label>
```

`GroupManager`에 `handleUpdateShareSettings` 추가 → `groupsApi.updateShareSettings` 호출 후 `refresh(kind)`. props 체인(`GroupSection`→`GroupCard`)에 `onUpdateShareSettings` 전달. `handleEnableShare` 시그니처에 `showTransactions` 추가.

- [ ] **Step 5: 통과 확인**

Run: `cd frontend && npm test -- GroupManager && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api.ts frontend/components/groups/GroupManager.tsx frontend/__tests__/components/GroupManager.share.test.tsx
git commit -m "feat(share): add transaction-visibility option to group share UI"
```

---

## Task 11: 전체 검증 + 수동 확인

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 2: 프론트 전체 테스트 + 타입 + 빌드**

Run: `cd frontend && npm test && npx tsc --noEmit && npm run build`
Expected: PASS, 빌드 성공.

- [ ] **Step 3: 수동 시나리오(선택, preview 또는 로컬)**

1. 그룹 공유 생성(거래내역 OFF) → 공유 URL 접속 → 보유 종목 클릭 → 상세 진입(삭제/거래 폼 없음, 거래내역 섹션 없음).
2. GroupManager에서 "거래내역 공개" 토글 ON → 공유 상세 새로고침 → 거래 내역 섹션 표시, 스코프 내 거래만.
3. requires_auth 공유 → 비로그인 상세 접속 → 로그인 안내.
4. 스코프 밖 holding_id 직접 접근 → 404.

- [ ] **Step 4: 최종 커밋(필요 시) 및 브랜치 정리**

`superpowers:finishing-a-development-branch`로 병합/PR 결정.

---

## Self-Review 결과 (작성자 점검)

- **스펙 커버리지**: #1 네비게이션 → Task 5(holding_id)·7(링크 prop)·9(라우트). #2 읽기전용+스코프 → Task 4(스코프 계산)·6(GET 전용·스코프검증)·9(삭제/폼 부재). #3 거래내역 옵션 → Task 1~3(컬럼/API/PATCH)·6(게이트)·9(섹션)·10(UI). 모두 매핑됨.
- **보유수량(반영 완료)**: `SharedHoldingDetailOut.remaining_quantity`(Task 5 스키마, Task 6에서 group_breakdown 잔여수량 합으로 산출, Task 9에서 `quantity={holding.remaining_quantity}` 연결)로 처리됨.
- **타입 일관성**: 백엔드 `SharedHoldingDetailOut`(performance/group_breakdown/snapshots/transactions) ↔ 프론트 `SharedHoldingDetail` 필드명 일치 확인. `HoldingPerformance`/`HoldingGroupBreakdown` 프론트 타입은 백엔드 `*Out`과 동일 필드.
- **플레이스홀더 스캔**: 마크업 복사 지시(Task 8 Step 2, Task 10 테스트)는 기존 코드 출처를 명시했으므로 허용 범위. 실제 실행 시 해당 블록을 그대로 복사.
- **순환 import**: groups.py → holdings.py 단방향 확인. 위험 시 함수 내부 지연 import 적용(Task 6에 명시).
