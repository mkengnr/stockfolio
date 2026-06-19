# 라벨 필터 + 그룹 색상 추천 + 그룹관리 인라인 수정 설계

작성일: 2026-06-19
브랜치: `label-filter-and-group-color`

## 배경

세 가지 UX 개선을 한 묶음으로 진행한다.

- **A. 라벨 그룹 필터**: 대시보드 그룹 필터가 출처그룹·통합(rollup)그룹은 지원하지만 라벨은 누락돼, 특정 라벨로 포트폴리오를 좁혀 볼 수 없다.
- **B. 그룹 색상 추천 + 프리셋**: 새 그룹 생성 시 색상 기본값이 항상 `#6366f1`(파랑)로 고정돼, 기존 그룹과 색이 겹친다. 또 색 선택이 네이티브 피커뿐이라 고르기 번거롭다.
- **C. 그룹관리 인라인 수정**: "수정"을 누르면 화면 상단의 별도 수정 카드로 점프해 사용이 불편하다. 누른 카드 자리에서 바로 편집하고 싶다.

## 현재 구조 (검증됨)

- 대시보드 그룹 종류: `DashboardGroupKind = Literal["source", "combined", "unclassified"]` — 라벨 없음 (`backend/app/schemas/dashboard.py:12`).
- 대시보드는 모든 출처·통합 그룹의 요약·보유·히스토리를 **사전 계산**해 `dashboard.groups`에 담아 보내고, 프론트는 재조회 없이 전환만 한다 (`DashboardOverview.tsx:57`, `app/share/[token]/page.tsx`).
- 백엔드 스코프 엔진은 이미 `label`을 지원한다: `resolve_portfolio_scope`가 label kind 처리(`portfolio.py:224`), 거래에 `label_ids` 전달(`portfolio.py:272`). 라벨 스코프 대시보드 산출 함수 `build_scoped_portfolio_dashboard`(`portfolio.py:1318`)가 이미 존재하며 공유 경로(`build_shared_portfolio_dashboard`)가 이를 래핑한다.
- 라벨은 거래 단위 다대다(`TransactionLabel` 조인, `group.py:157`). 출처그룹은 거래당 1개(완전 분할), 통합그룹은 출처들의 집계. 라벨은 **중첩/교차 태그**라 합산 시 중복이 불가피하다.
- 그룹관리(`GroupManager.tsx`): 상단 "새 그룹 만들기" 카드 + `{editing && <Card>수정</Card>}` 별도 카드(`:206`) + 카드 그리드(`GroupCard`). 색상 입력은 네이티브 `<input type="color">`(`ColorInput`, `:248`). `DEFAULT_COLOR = '#6366f1'`(`:14`). SWR로 sources/rollups/labels 모두 이미 로드.

## A. 라벨 그룹 필터

### 범위
**인증된 본인 대시보드(`DashboardOverview`)에만** 적용한다. 공유 페이지의 라벨 필터는 공개 토큰에서 임의 라벨을 온디맨드 조회하는 데이터 노출 검토가 추가로 필요하므로 이번 범위에서 제외한다(후속 과제).

### 데이터 로딩: 온디맨드
출처/통합처럼 모든 라벨을 사전 계산해 payload에 싣지 않는다. 라벨 선택 시 그 라벨 스코프 대시보드를 그때 조회한다. 라벨 수가 많아도 응답이 가볍고, 비교 테이블·구성 차트에 중첩 데이터를 섞지 않는다.

### 백엔드
- 신설 엔드포인트: `GET /api/portfolio/labels/{label_id}/dashboard?display_currency=KRW` → `DashboardResponse` 반환.
  - 포트폴리오 라우터 prefix `/api/portfolio`(검증됨, `portfolio.py:54`)를 따른다. `display_currency` 쿼리 파라미터는 기존 `/api/portfolio/dashboard`와 동일하게 받는다.
  - 소유자 검증 필수(`label.user_id == current_user.id`, 불일치/없음 시 404).
  - 내부적으로 기존 `build_scoped_portfolio_dashboard`를 label 스코프로 호출한다. 신규 회계/집계 로직은 없다.
  - 응답은 기존 대시보드와 동일 형태: `summary`/`history`/`holdings` 채움, `groups`는 비움(라벨 스코프는 내부 하위 그룹 분해 안 함).

### 프론트엔드 (`DashboardOverview`)
- `GroupFilterMenu` 옵션을 섹션 구조로 확장: `출처 그룹 / 통합 그룹 / 라벨` 헤더 구분. 라벨 0개면 라벨 섹션 숨김. 라벨 옵션 값은 `label:{id}` 형태로 출처/통합 키와 구분한다.
- 선택 상태:
  - `total` 또는 출처/통합 그룹 키 → 기존처럼 사전계산된 `dashboard.groups`에서 즉시 전환.
  - `label:{id}` → SWR로 `GET /api/portfolio/labels/{id}/dashboard` 조회. 로딩 중에는 차트/요약/표 영역에 로딩 표시. 성공 시 그 응답의 `summary`/`history`/`holdings`로 렌더.
- 라벨 선택 시:
  - 구성 막대그래프 off (`includeComposition={false}` — 출처 그룹 선택 때와 동일 취급).
  - 비교 테이블(`GroupPerformanceTable`)·구성 차트에는 라벨을 **넣지 않는다**(중복 합산 혼란 방지). 비교 테이블은 기존 출처·통합만 유지.
- 그룹이 사라진 reload 시 선택 초기화 로직(`selectedGroupKey` reset)은 라벨 키에도 동일 적용.
- 원금 기준 토글·차트 기간 등 기존 컨트롤은 그대로 동작.

### GroupFilterMenu
- `options`를 평면 배열에서 `{ section?: string; value; label }[]` 또는 그룹화 가능한 형태로 확장. 섹션 헤더는 비선택 라벨 행으로 렌더. 단일 선택 동작·키보드 접근성 유지.

## B. 그룹 색상 추천 + 프리셋

### 프리셋 팔레트
공용 상수로 12색 정의(프론트):
```
indigo #6366f1, blue #3b82f6, cyan #06b6d4, teal #14b8a6,
emerald #10b981, lime #84cc16, amber #f59e0b, orange #f97316,
red #ef4444, pink #ec4899, violet #8b5cf6, purple #a855f7
```
(그룹 배지 식별색이므로 손익 색 관례와 무관하게 레드/블루 포함 가능.)

### 스마트 기본값
- 범위 기준: **전체 그룹(sources + rollups + labels) 통틀어** 이미 쓰는 색.
- 새 그룹 생성 폼을 열 때 `color` 기본값 = 프리셋 순서상 **아직 안 쓰는 첫 색**.
- 모든 프리셋이 사용 중이면 첫 프리셋(`#6366f1`)으로 폴백.
- 사용 색 집합은 GroupManager가 이미 SWR로 로드한 sources/rollups/labels의 `color`를 소문자 정규화해 산출. 데이터 로드 전이면 첫 프리셋.
- 헬퍼 `recommendGroupColor(usedColors: string[]): string`로 순수 함수 분리(단위 테스트 대상).

### ColorInput 개선
- 기존 네이티브 `<input type="color">`(커스텀)는 유지하고, 그 위/옆에 **프리셋 스와치 버튼 행** 추가.
  - 스와치 클릭 → 해당 색 선택.
  - 현재 선택 색은 외곽선 표시.
  - 이미 사용 중인 색은 흐리게 + 작은 체크로 "사용중" 표시(클릭은 여전히 가능 — 강제 금지는 아님).
- `ColorInput`에 `usedColors?: string[]` prop 추가(사용중 표시용). 생성·수정 폼 모두 프리셋 제공. 스마트 기본값은 **생성 시에만**(수정은 현재 색 유지).
- 접근성: 각 스와치는 `button` + `aria-label`(색 이름/HEX), `aria-pressed`로 선택 상태.

## C. 그룹관리 인라인 수정

### 변경
상단 별도 수정 카드(`GroupManager.tsx:206`)를 제거하고, 수정 버튼을 누른 `GroupCard`가 **제자리에서** 인라인 편집 폼으로 전환한다.

- 편집 상태를 `GroupCard` 단위로 관리(누른 카드만 편집 모드).
- 편집 모드 시 카드 본문 → 인라인 폼: 이름·설명·색상(프리셋 ColorInput)·공유 문구, 통합그룹이면 `MemberSelector`. `저장`/`취소` 버튼.
- 저장: 업데이트 API 호출 → 성공 시 폼 닫고 목록 갱신, 실패 시 카드 내 에러 표시.
- 취소: 폼 닫고 원래 카드로 복귀.
- 그리드 레이아웃은 그대로. 편집 카드만 폼 높이만큼 늘어난다.
- 편집 상태는 카드별 독립 토글로 관리한다(`GroupCard` 로컬 상태). 여러 카드를 동시에 열어 편집해도 무방하며 각 카드가 독립적으로 저장한다. 별도의 "한 번에 하나만" 강제는 두지 않는다.

### 상태/리팩토링
- 부모(`GroupManager`)의 `editing`/`editName`/`editColor`/`editDescription`/`editShareDescription`/`editMemberIds`/`startEdit` 및 별도 수정 카드 JSX 제거.
- 업데이트 로직(`handleUpdate`)은 `onSave(kind, group, payload)` 형태 콜백으로 정리해 `GroupCard`에서 호출. 편집 폼 입력 상태는 `GroupCard` 로컬에서 관리(초기값 = 해당 group 값).
- `MemberSelector`는 통합그룹 편집에서 재사용.

## 컴포넌트/인터페이스 요약

- `recommendGroupColor(used: string[]): string` — 순수 함수 (B).
- `GROUP_COLOR_PRESETS: { value: string; name: string }[]` — 공용 상수 (B).
- `ColorInput({ label, value, onChange, usedColors? })` — 프리셋 스와치 포함 (B, C에서 재사용).
- `GroupFilterMenu` — 섹션 옵션 지원 (A).
- `GroupCard` — 인라인 편집 모드 + 로컬 폼 상태 (C).
- 백엔드 `GET /api/portfolio/labels/{label_id}/dashboard` (A).

## 데이터 흐름

- A: 라벨 선택 → SWR fetch(label dashboard) → DashboardOverview가 그 응답으로 요약/차트/표 렌더. 출처/통합/전체는 기존 사전계산 경로 유지.
- B: 생성 폼 오픈 → `recommendGroupColor(usedColors)`로 기본색 산출 → ColorInput에 프리셋+사용중 표시.
- C: 카드 수정 클릭 → 카드 로컬 편집 상태 on → 폼 → 저장 → `onSave` → API → SWR mutate.

## 에러 처리

- A: 라벨 대시보드 조회 실패 시 차트/표 영역에 에러 메시지 + 재시도. 소유자 불일치/없음 → 404 → "라벨을 찾을 수 없습니다".
- B: 추천 색 산출은 실패해도 첫 프리셋으로 폴백(예외 없음).
- C: 저장 실패 시 편집 폼 유지 + 카드 내 에러. 낙관적 갱신 안 함(저장 성공 후 mutate).

## 테스트 (TDD)

- 백엔드:
  - 라벨 대시보드 엔드포인트: 소유 라벨 → 스코프 요약/보유 반환; 타 사용자 라벨 → 404; 라벨에 거래 없는 종목 제외 등 스코프 정확성. `build_scoped_portfolio_dashboard` 기존 테스트 패턴 재사용.
- 프론트:
  - `recommendGroupColor`: 빈 사용목록→첫 프리셋, 일부 사용→첫 미사용, 전부 사용→첫 프리셋 폴백, 대소문자 정규화.
  - `GroupFilterMenu`: 라벨 섹션 렌더, 라벨 0개 시 섹션 숨김, 라벨 선택 콜백.
  - `DashboardOverview`: 라벨 선택 시 라벨 대시보드 fetch 호출 + 렌더, 구성차트 off, 비교 테이블에 라벨 미포함.
  - `ColorInput`: 프리셋 스와치 렌더, 클릭 시 onChange, 사용중 표시.
  - `GroupManager`/`GroupCard`: 수정 클릭 시 카드 내 인라인 폼 노출(상단 점프 없음), 저장/취소 동작, 저장 실패 에러.

## YAGNI / 비범위

- 공유 페이지 라벨 필터(후속).
- 라벨 다중 선택(AND/OR), 라벨끼리 비교(전용 화면이 필요한 별도 과제).
- 색상 강제 중복 금지(사용중 색도 선택 허용).
- 인라인 편집 시 카드 풀폭 확장/모달(그리드 셀 내 확장으로 충분).
