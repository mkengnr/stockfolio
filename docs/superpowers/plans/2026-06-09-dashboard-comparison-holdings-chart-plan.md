# 대시보드 비교 기준, 그룹별 보유종목, 통합 차트 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드 조회 시 직전 거래일 스냅샷을 복구하고, 선택 그룹의 실제 잔여 lot 보유값을 표시하며, 그룹 누적 평가금액과 평가금액/투자원금 선 및 일별 손익 막대를 결합한 차트를 제공한다.

**Architecture:** 백엔드는 현재가 기준일 이전의 짧은 이력 구간만 조회해 누락 스냅샷을 추가하고, 기존 lot 회계 범위 계산을 재사용해 각 그룹 요약에 범위별 보유종목을 포함한다. 프론트엔드는 `DashboardHistoryRow`에서 중복 없는 그룹 누적 시리즈와 선택 범위의 선/손익 막대 시리즈를 파생하고 TradingView Lightweight Charts의 단일 시간축에 상단/하단 가격 스케일을 배치한다.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, pytest, Next.js 14, TypeScript, Jest, Testing Library, TradingView Lightweight Charts

---

### Task 1: 조회 시 직전 거래일 스냅샷 복구

**Files:**
- Modify: `backend/app/routers/portfolio.py`
- Modify: `backend/app/services/snapshot_service.py`
- Test: `backend/tests/test_snapshot_service.py`
- Test: `backend/tests/test_dashboard_aggregate.py`

- [ ] **Step 1: 직전 거래일 후보 스냅샷을 추가하는 실패 테스트 작성**

`backend/tests/test_snapshot_service.py`에 현재가 기준일 전날까지 최근 7일 가격 이력을 조회하고, 그중 누락된 거래일 스냅샷만 추가하는 `backfill_recent_comparison_snapshots` 테스트를 추가한다. 이미 최신 거래일 스냅샷이 있으면 추가하지 않는 테스트도 작성한다.

- [ ] **Step 2: 백엔드 단위 테스트를 실행해 RED 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_snapshot_service.py -q`

Expected: 새 복구 함수 import 또는 기대 호출이 없어 FAIL.

- [ ] **Step 3: 최근 비교 스냅샷 복구 함수 최소 구현**

`backend/app/services/snapshot_service.py`에 현재가 기준일 이전 7일 구간을 대상으로 기존 `backfill_holding_snapshots`를 재사용하는 함수를 추가한다. 현재가 기준일 당일 스냅샷은 비교 대상으로 추가하지 않는다.

- [ ] **Step 4: 대시보드 조회 복구 흐름 실패 테스트 작성**

`backend/tests/test_dashboard_aggregate.py`에 다음을 검증하는 테스트를 추가한다.

- 현재가 기준일 이전 스냅샷이 오래되었으면 활성 보유종목 복구를 실행하고 커밋한 뒤 보유종목을 다시 로드한다.
- 복구가 실패하면 응답 경고에 종목과 직전 거래일 복구 실패 내용을 추가한다.
- 최근 스냅샷이 있으면 복구를 생략한다.

- [ ] **Step 5: 대시보드 복구 흐름 구현 및 GREEN 확인**

`build_portfolio_dashboard_response`에서 시세 날짜를 결정한 뒤 필요한 보유종목만 복구한다. 추가 데이터가 있으면 `db.commit()` 후 보유종목을 다시 로드한다. 실패는 경고로 변환한다.

Run: `cd backend && .venv/bin/python -m pytest tests/test_snapshot_service.py tests/test_dashboard_aggregate.py -q`

Expected: PASS.

### Task 2: 그룹 범위별 보유종목 API

**Files:**
- Modify: `backend/app/schemas/dashboard.py`
- Modify: `backend/app/routers/portfolio.py`
- Modify: `backend/tests/test_dashboard_aggregate.py`
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: 그룹별 보유종목 실패 테스트 작성**

`backend/tests/test_dashboard_aggregate.py`에 한 종목이 두 출처 그룹과 미분류 lot를 함께 가진 사례를 추가한다. 출처 그룹, 통합 그룹, 미분류의 `group.holdings`가 각각 해당 범위의 수량, 잔여원금, 평가금액, 평가손익만 포함하는지 검증한다.

- [ ] **Step 2: 테스트를 실행해 RED 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py -q`

Expected: `DashboardGroupSummary.holdings`가 없어 FAIL.

- [ ] **Step 3: 그룹 요약에 범위별 보유종목 구현**

`DashboardGroupSummary`에 `holdings: list[DashboardHoldingRow]`를 추가한다. `_build_dashboard_holdings`가 `PortfolioScope`를 인자로 받아 기존 `_build_scoped_dashboard_payload`로 범위별 행을 만들도록 변경하고, 각 그룹 생성 시 해당 범위의 보유종목을 연결한다.

- [ ] **Step 4: 백엔드 테스트 GREEN 및 프론트엔드 타입 동기화**

Run: `cd backend && .venv/bin/python -m pytest tests/test_dashboard_aggregate.py -q`

Expected: PASS.

`frontend/lib/types.ts`의 `DashboardGroupSummary`에 `holdings: DashboardHoldingRow[]`를 추가한다.

### Task 3: 선택 그룹 보유종목 표시 및 비교 라벨

**Files:**
- Modify: `frontend/components/dashboard/DashboardOverview.tsx`
- Modify: `frontend/__tests__/dashboard/DashboardOverview.test.tsx`

- [ ] **Step 1: 선택 그룹의 범위별 보유값과 비교 라벨 실패 테스트 작성**

그룹의 `holdings`에 전체 종목 값과 다른 수량/금액을 넣고 그룹 선택 후 그 값이 표시되는지 검증한다. `비교 기준(직전 거래일)` 라벨도 검증한다.

- [ ] **Step 2: 프론트엔드 테스트 RED 확인**

Run: `cd frontend && npm test -- --runInBand __tests__/dashboard/DashboardOverview.test.tsx`

Expected: 기존 클라이언트 필터가 전체 보유값을 사용하고 라벨이 달라 FAIL.

- [ ] **Step 3: 그룹 보유종목 전환 구현**

`DashboardOverview`에서 전체 선택 시 `dashboard.holdings`, 그룹 선택 시 `selectedGroup.holdings`를 사용한다. 기존 `filterHoldingsByGroup`는 제거한다. 비교 라벨을 변경한다.

- [ ] **Step 4: 프론트엔드 테스트 GREEN 확인**

Run: `cd frontend && npm test -- --runInBand __tests__/dashboard/DashboardOverview.test.tsx`

Expected: PASS.

### Task 4: 통합 차트 시리즈 생성기

**Files:**
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Modify: `frontend/__tests__/dashboard/PortfolioChart.test.ts`

- [ ] **Step 1: 통합 시리즈 실패 테스트 작성**

다음 순수 함수 동작을 테스트한다.

- 선택 범위의 평가금액 및 투자원금 선 생성
- 연속 거래일의 `total_profit_loss` 차이로 일별 손익 생성
- 전체 범위에서 출처 그룹 및 미분류만 누적 막대 시리즈로 생성
- 통합 그룹 제외
- 숫자 포맷 함수가 `1234567.89`를 `1,234,568`로 표시

- [ ] **Step 2: 차트 테스트 RED 확인**

Run: `cd frontend && npm test -- --runInBand __tests__/dashboard/PortfolioChart.test.ts`

Expected: 새 통합 시리즈 생성기와 포맷 함수가 없어 FAIL.

- [ ] **Step 3: 순수 시리즈 생성기 최소 구현**

`PortfolioChart.tsx`에서 기존 대시보드 단일 지표 시리즈 생성기를 통합 차트 데이터 생성기로 교체한다. 날짜 정렬과 null 제외를 명시적으로 처리한다.

- [ ] **Step 4: 차트 단위 테스트 GREEN 확인**

Run: `cd frontend && npm test -- --runInBand __tests__/dashboard/PortfolioChart.test.ts`

Expected: PASS.

### Task 5: 통합 차트 UI

**Files:**
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Modify: `frontend/components/dashboard/DashboardOverview.tsx`
- Delete: `frontend/components/dashboard/DashboardChartControls.tsx`
- Modify: `frontend/__tests__/dashboard/DashboardOverview.test.tsx`

- [ ] **Step 1: 통합 차트 props 및 컨트롤 제거 실패 테스트 작성**

`DashboardOverview` 테스트 mock이 선택 범위 행과 전체 이력 행을 받는지 확인하고, 기존 `하나의 차트`, `각각 보기`, 단일 지표 버튼이 더 이상 표시되지 않는지 검증한다.

- [ ] **Step 2: 테스트 RED 확인**

Run: `cd frontend && npm test -- --runInBand __tests__/dashboard/DashboardOverview.test.tsx`

Expected: 기존 컨트롤과 props 때문에 FAIL.

- [ ] **Step 3: TradingView 통합 차트 구현**

상단에 출처 그룹/미분류 누적 histogram, 전체 평가금액 실선, 투자원금 점선을 추가한다. 하단 별도 가격 스케일에 일별 손익 histogram을 배치한다. `priceFormat`과 localization formatter에 정수 콤마 포맷을 적용한다. 그룹 선택 시 누적 막대는 숨기고 선택 범위 선과 손익 막대만 표시한다.

- [ ] **Step 4: 대시보드에서 기존 차트 컨트롤 제거 및 새 props 연결**

기간 선택은 유지하고 `PortfolioChart`에 선택 범위 이력과 전체 이력을 전달한다. 더 이상 사용하지 않는 `DashboardChartControls.tsx`를 삭제한다.

- [ ] **Step 5: 프론트엔드 관련 테스트 GREEN 확인**

Run: `cd frontend && npm test -- --runInBand __tests__/dashboard/DashboardOverview.test.tsx __tests__/dashboard/PortfolioChart.test.ts`

Expected: PASS.

### Task 6: 전체 검증 및 리뷰

**Files:**
- Modify only if verification or review reveals defects.

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `cd backend && .venv/bin/python -m pytest tests/`

Expected: PASS.

- [ ] **Step 2: 프론트엔드 전체 테스트와 빌드**

Run: `cd frontend && npm test -- --runInBand`

Expected: PASS.

Run: `cd frontend && npm run build`

Expected: PASS.

- [ ] **Step 3: 로컬 대시보드 시각 검증**

실행 중인 로컬 앱이 있으면 Browser 플러그인으로 대시보드를 열어 누적 막대, 선, 하단 손익 패널, 그룹별 보유값 전환을 확인한다.

- [ ] **Step 4: 코드 리뷰 요청 및 중요 이슈 반영**

승인된 설계 문서와 구현 diff를 기준으로 리뷰를 요청한다. Critical 및 Important 이슈를 수정하고 관련 테스트를 다시 실행한다.
