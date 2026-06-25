# 포트폴리오 차트 호버 툴팁 + ISO 날짜 표시 — 설계

작성일: 2026-06-25

## 목표

대시보드 포트폴리오 차트(`DashboardPortfolioChart`)에 두 기능을 추가한다.

1. **호버 툴팁 박스**: 평가금액(메인) 차트에 마우스 오버 시, 해당 날짜의 5개 지표를 박스로 표시
   - 평가금액, 총손익, 총손익율, 일별손익, 투자원금(또는 잔여원금)
2. **ISO 날짜 표시**: 호버 시 크로스헤어 날짜 라벨을 `YYYY-MM-DD`(년-월-일) 순서로 표시 (기존: 영어식 일-월-년)

## 대상 파일

- `frontend/components/dashboard/PortfolioChart.tsx` — `DashboardPortfolioChart` 컴포넌트
- `frontend/__tests__/dashboard/` — 단위 테스트 추가

## 결정 사항 (사용자 확인됨)

- **날짜 형식**: `2026-06-25` (ISO). 툴팁 헤더 + 크로스헤어 라벨 양쪽.
- **툴팁 범위**: 평가금액(메인) 차트 호버 시에만. 일별손익 차트에는 붙이지 않음.
- **총손익율 / 원금 기준**: 차트의 `투자원금 / 잔여원금` 토글(`referenceField`)을 그대로 추종.
  - 토글이 `invested` → 기준원금 = `total_invested_principal`, 라벨 "투자원금"
  - 토글이 `cost` → 기준원금 = `total_cost_basis`, 라벨 "잔여원금"

## 데이터

`DashboardHistoryRow`(날짜별, 문자열|null):
`total_value`, `total_invested_principal`, `total_cost_basis`, `total_profit_loss`.

일별손익은 이미 계산된 `chartData.dailyProfitChange`(요소: `{time, value, color}` 또는 whitespace `{time}`)에서 날짜로 조회.

## 컴포넌트 / 데이터 흐름

### 1. 날짜별 지표 맵 (순수 함수)

`buildTooltipData(rows, dailyProfitChange, referenceField)` → `Map<'YYYY-MM-DD', TooltipDatum>`.
`useMemo`로 빌드. 소스: `selectedMerge.rows` + `chartData.dailyProfitChange`.

`TooltipDatum` 필드와 계산:

| 행 | 계산 |
|---|---|
| 평가금액 | `total_value` |
| 총손익 | `total_profit_loss` |
| 총손익율 | `total_profit_loss ÷ 기준원금 × 100` |
| 일별손익 | `dailyProfitChange`에서 해당 날짜의 `value` |
| 투자원금/잔여원금 | 기준원금 값 + 라벨 `referenceFieldLabel[referenceField]` |

- 기준원금 = `referenceField === 'invested' ? total_invested_principal : total_cost_basis`
- null/0 값 → `-` 표시. 기준원금이 null 또는 0(전량 재투자)이면 율은 `-`.
- 금액 포맷은 기존 `formatDashboardMoney` 재사용. 율은 소수 2자리 + `%`.

### 2. 툴팁 박스 (imperative DOM)

- `mainContainerRef`를 `position: relative` 부모로 감싸고, 내부에 absolute `div`(`tooltipRef`).
- 크로스헤어 이벤트가 빈번하므로 **React state 대신 직접 DOM 갱신** → 차트 `useEffect` 의존성/재생성 회피.
- 스타일: 기존 톤(흰 배경, `text-xs`, 회색 텍스트, 얇은 테두리·그림자). 헤더에 ISO 날짜, 본문에 5개 행(라벨 + 값). 손익/율 부호에 따라 색상(양수 red 계열, 음수 blue 계열 — 기존 일별손익 색 규칙과 일치).

### 3. 크로스헤어 핸들러

`mainChart.subscribeCrosshairMove(handler)`:

- `param.point` 또는 `param.time`이 없으면 → 툴팁 숨김.
- `toIsoDateKey(param.time)`로 ISO 키 변환:
  - 문자열이면 그대로 사용 (v4는 `originalTime`을 전달하므로 ISO 입력 시 보통 문자열로 옴 — Codex 소스 확인).
  - `BusinessDay` 객체(`{year, month, day}`)면 zero-pad하여 `YYYY-MM-DD` 생성 (타입 안전 가드).
  - 그 외(UTCTimestamp 숫자 등) 예상치 못한 형태면 숨김 처리.
- Map 조회 → 내용 갱신. 위치는 `param.point.x/y` 기준, 차트 경계 클램핑(박스가 오른쪽/아래로 넘치면 반대편으로 뒤집음).

### 4. ISO 날짜 라벨

- 두 차트 `createChart` 옵션에 `localization: { ...priceFormatter, dateFormat: 'yyyy-MM-dd' }` 추가 → 크로스헤어 날짜 라벨이 `2026-06-25` 순서.
- 축 눈금이 과도하게 길어지면 `timeScale.tickMarkFormatter`로 분리 (Codex 확인: `dateFormat`과 tickMark 포매터는 별개). **구현 시 preview로 실제 렌더 확인 후 필요 시 적용.**

### 5. Cleanup

- teardown에 `mainChart.unsubscribeCrosshairMove(handler)` 추가 (기존 unsubscribe/`remove()` 패턴과 함께).
- 툴팁 `div`는 JSX로 렌더되어 React가 언마운트 시 정리.

## 에러 처리

- 결측/null 지표 → `-`.
- 투자원금 0(전량 재투자) → 율 `-`.
- 알 수 없는 `param.time` 형태 → 툴팁 숨김(조용히 무시).

## 기존 구조와의 충돌 검토

- 로지컬레인지 동기화 + 데이트 스파인 = **시간축 동기화** 로직. 툴팁은 **읽기 전용 크로스헤어 구독**이라 상호 영향 없음.
- 툴팁은 메인 차트에만 부착, 일별손익 차트는 변경 없음.

## 테스트 전략 (TDD)

`PortfolioChart`는 `lightweight-charts`를 동적 import → jsdom에서 차트 렌더 테스트 곤란. 따라서 로직을 순수 함수로 추출해 단위 테스트:

1. `buildTooltipData` — 지표 계산, 토글별 기준원금/라벨, null·0 처리, 일별손익 매칭.
2. `toIsoDateKey` — 문자열 / `BusinessDay` 객체 / 비정상 입력.
3. 율·금액 포맷 함수.

기존 `__tests__/dashboard/PortfolioChartLegend.test.tsx` 패턴 준수.

## 리뷰

구현 완료 후 Codex 리뷰(`/codex:review` 또는 rescue) 받아 함께 검토.
