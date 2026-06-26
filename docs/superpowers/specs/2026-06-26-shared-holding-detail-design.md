# 공유 페이지 종목 상세 (읽기 전용) + 거래내역 공유 옵션

작성일: 2026-06-26

## 배경 / 목표

공유 페이지(`/share/[token]`)는 그룹 단위 포트폴리오를 외부에 읽기 전용으로 노출한다.
현재 보유 종목 테이블은 보이지만 개별 **종목 상세 페이지로 이동할 수 없다**.

본 작업의 목표:

1. 공유 페이지의 종목 행에서 종목 상세 페이지로 이동할 수 있게 한다.
2. 공유로 보는 종목 상세는 **읽기 전용**이다. 종목 삭제 / 거래내역 등록·수정·삭제 등
   데이터 변경 기능이 전혀 없어야 한다. 그리고 **공유된 그룹 스코프와 관련된 데이터만** 보여야 한다.
3. 공유 옵션에 **거래내역 노출 여부**(`share_show_transactions`)를 추가한다.

## 결정 사항 (확정)

- **거래내역 표시 기본값**: OFF. 명시적으로 켜야만 공유됨. 마이그레이션 `server_default="false"`.
- **옵션 편집 방식**: 공유가 활성화된 상태에서도 토글 가능(토큰 재발급 없음). 신규 PATCH 엔드포인트.
- **거래내역 OFF일 때 상세 페이지**: 접근 가능. 가격차트 + 스코프 성과요약 + 그룹별 현황은 보이고,
  "거래 내역" 섹션과 차트의 매수/매도 마커만 숨긴다. (네비게이션 #1·읽기전용 #2는 거래내역 옵션 #3과 독립)

## 범위

- **대상**: 그룹 공유 — source / rollup / label (`/api/groups/share/{token}`).
- **비대상**: 레거시 태그 공유(`/api/share/{token}` → `SharedTag`). 종목 테이블 자체가 없어 변경 없음.

## 백엔드 설계

### 1. 모델 + 마이그레이션

`source_groups`, `rollup_groups`, `labels` 세 테이블에 컬럼 추가:

```python
share_show_transactions: Mapped[bool] = mapped_column(
    Boolean, nullable=False, server_default="false", default=False
)
```

Alembic autogenerate 후 `server_default` 명시 확인(기존 행 backfill). 세 테이블 모두.

### 2. 공유 옵션 API

- `ShareUpdateIn`에 `show_transactions: bool = False` 추가.
- `enable_share` (POST `/api/groups/{kind}/{entity_id}/share`): 생성 시 `share_show_transactions` 저장.
- **신규 PATCH** `/api/groups/{kind}/{entity_id}/share`: 활성 공유의 옵션을 in-place 변경.
  - Body `ShareSettingsUpdateIn { requires_auth: bool | None, show_transactions: bool | None }`
    (model_fields_set 기반 부분 업데이트). 토큰은 건드리지 않음.
  - 공유가 비활성(`share_token is None`)이면 404/409 처리.
  - 응답: `GroupOut` (현재 상태 반영).
- `GroupMetadataOut`에 `share_show_transactions: bool` 노출 (프론트 UI 현재 상태 표시).

### 3. 종목 상세 공유 엔드포인트 (신규)

`GET /api/groups/share/{token}/holdings/{holding_id}` → `SharedHoldingDetailOut`

처리 순서:

1. 토큰으로 entity 조회(source→rollup→label 순, `get_shared_group`과 동일 패턴). 없으면 404.
2. `share_requires_auth and current_user is None` → 401 (`get_current_user_optional` 사용).
3. `resolve_portfolio_scope(db, entity.user_id, public_kind, entity.id)` 로 스코프 해석.
4. holding 로드(`entity.user_id` 소유, `_holding_load_options()` + snapshots).
   holding이 없으면 404.
5. **스코프 검증**: 해당 holding이 스코프 내에 lot/거래가 존재하는지 확인.
   없으면 404 (소유자의 스코프 밖 종목 누출 방지).
6. 스코프 기준 성과요약 + 그룹별 현황 계산 (아래 4번).
7. 거래내역: `entity.share_show_transactions` 가 true일 때만, **스코프 내 거래만**,
   읽기 전용 최소 형태로 반환. false면 빈 배열 + `show_transactions=false` 플래그.
8. 스냅샷: `close_price` 시계열만 반환 (시장 공개 데이터). 전체 보유 `total_value`는
   스코프 누출이므로 제외.

응답 스키마(개략):

```python
class SharedHoldingDetailOut(BaseModel):
    ticker: str
    name: str
    market: Market
    currency: Currency
    current_price: Decimal | None
    show_transactions: bool
    performance: SharedHoldingPerformanceOut | None  # 스코프 기준
    group_breakdown: list[SharedHoldingGroupBreakdownOut]  # 스코프 내 그룹만
    snapshots: list[SharedSnapshotOut]  # snapshot_date, close_price
    transactions: list[SharedTransactionOut]  # show_transactions=false면 []
```

`SharedTransactionOut` 필드: `type`, `transaction_date`, `quantity`, `price`, `amount(=quantity*price)`.
(소유자 전용 분류/라벨/검토상태/lot 정보는 미포함.)

### 4. 스코프 기준 성과 계산

기존 `holdings.py::_holding_performance(holding, current_price, source_groups)` 는
투자원금에 `PortfolioScope("all")`을 하드코딩하고 모든 lot을 순회한다.
이를 **scope 인자를 받도록 일반화**:

- `_holding_performance(holding, current_price, source_groups, scope=PortfolioScope("all"))`
- 투자원금: `_scope_invested_principal(transactions, holding, scope)`
- `remaining_cost_basis` / `remaining_quantity` / 평가금액: `replay_result.lots` 중
  `lot_accounting` 스코프 predicate(`_lot_in_scope` 류)로 **스코프 내 lot만** 합산.
- 그룹별 현황(`group_breakdown`): 스코프 내 lot만 source_group별로 묶음.
  - source 공유 → 해당 그룹 1개
  - rollup 공유 → 멤버 source 그룹들
  - label 공유 → 스코프 내 lot들의 출처 그룹들(미분류 포함 가능)
- 기존 호출부 `get_holding` 은 인자 없이 호출 → 기본값 `PortfolioScope("all")` 로 동작 불변.

> 주의: lot_accounting 의 스코프 predicate 가 `lot`/`transaction` 단위로 노출되어 있는지
> 확인하고, 없으면 holdings.py 내부에 스코프 필터 헬퍼를 둔다. label 스코프는 transaction의
> label_ids 기준 필터가 필요할 수 있다(구현 시 검증).

## 프론트엔드 설계

### 1. 종목 링크 노출

- `SharedDashboardHoldingOut`에 `holding_id: uuid.UUID` 추가.
- `groups.py::_public_dashboard_holding` 에서 `holding_id=holding.holding_id` 전달.
- `lib/types` `SharedDashboardHolding` 에 `holding_id` 추가.
- `lib/shareAdapters.ts::toDashboardHolding` 이 현재 `holding_id: null` → 실제 값 전달.
- `HoldingsTable` 에 `holdingHref?: (id: string) => string` prop 추가
  (기본값 `(id) => \`/holdings/${id}\``). `HoldingName` 의 링크가 이 prop 사용.
  → 대시보드 동작 불변(하위호환).
- 공유 페이지(`SharedGroupView`)는 `holdingHref={(id) => \`/share/${token}/holdings/${id}\`}` 주입.
  (token 을 `SharedGroupView` 까지 전달 필요.)

### 2. 신규 라우트

`frontend/app/share/[token]/holdings/[holdingId]/page.tsx`

- `AuthGuard` 없음 (공유 컨텍스트).
- `shareApi.getHolding(token, holdingId)` 로 페치 (`lib/api`에 추가).
- 401/404 처리는 기존 공유 페이지 패턴 재사용(로그인 필요 안내 포함).
- 레이아웃: 헤더(상위 공유 페이지로 돌아가기 링크 + 종목명, **삭제 버튼 없음**)
  + 성과요약(스코프) + 가격차트 + 그룹별현황(스코프) + (옵션 ON시) 읽기전용 거래내역.
- 기존 `TransactionList` 는 `holdingsApi`(소유자) + 삭제/분류편집과 강결합 → 재사용 불가.
  **읽기 전용 거래 테이블 신규 작성**(구분/날짜/수량/단가/금액).
- `HoldingPerformanceSummary`, `HoldingGroupBreakdownTable`, `PriceChart` 는 표현형 →
  공유 페이로드 형태에 맞게 재사용/소폭 일반화. (PriceChart 의 마커는 transactions가
  비어 있으면 자연히 표시 안 됨 → 옵션 OFF시 거래 빈 배열로 충족.)

### 3. 공유 설정 UI (GroupManager)

- 공유 생성 폼(미공유 카드): "거래내역 공개" 체크박스 추가(기본 OFF) → `enableShare` 에 전달.
- 공유 활성 카드: "거래내역 공개" 토글 추가 → 신규 `groupsApi.updateShareSettings(kind, id, {...})`
  (PATCH) 호출. 기존 "로그인 필요" 표시 옆에 현재 상태 표기.
- `lib/api` `groupsApi.enableShare` 시그니처에 `showTransactions` 추가,
  `groupsApi.updateShareSettings` 신규.

## 영향도 / 리스크

- **보안 핵심**: 상세 엔드포인트의 (a) 스코프 검증, (b) requires_auth 게이트,
  (c) GET 전용(변경 불가), (d) 스코프 밖 거래/그룹 미노출 — 이 4가지가 누출 방지의 전부.
  반드시 테스트로 고정.
- 기존 대시보드/소유자 상세 페이지: prop 기본값 + 신규 컬럼 default 로 **동작 불변**.
- `_holding_performance` 시그니처 변경 → 기존 호출부(`get_holding`) 동시 점검.
- 마이그레이션 `server_default` 필수.

## 테스트 (TDD)

백엔드:
- 신규 GET 상세: 스코프 내 종목 정상 / 스코프 밖 종목 404 / requires_auth 401 /
  옵션 ON시 거래 반환·OFF시 빈 배열 / 스코프 밖 거래·그룹 미노출.
- PATCH 옵션: requires_auth·show_transactions 부분 업데이트, 토큰 불변, 비공유 그룹 거부.
- `_holding_performance` 스코프 계산(source/rollup/label 각각의 원금·평가·그룹별).
- 기존 `get_holding` 회귀(스코프 all 동일 결과).

프론트:
- 공유 테이블에서 종목명 링크 렌더(`holding_id` 존재 시) + href 가 `/share/{token}/holdings/...`.
- 공유 상세 페이지: 삭제 버튼/거래 등록 폼/거래 삭제 버튼 부재.
- 옵션 OFF시 "거래 내역" 섹션 부재, ON시 읽기 전용 테이블 표시.
- GroupManager: 거래내역 공개 토글 동작.
