# 종목 상세 차트 개선 — 현재가 · ISO 날짜 · 매수/매도 마커 · 호버 박스 설계

작성일: 2026-06-25

## 목표

종목 상세 페이지(`app/holdings/[id]/page.tsx`)의 가격 차트(`PriceChart`)에 다음을 추가한다.

1. **현재가 표시**: 일별 종가 시리즈를 오늘(현재가)까지 연장
2. **ISO 날짜**: 축·크로스헤어 날짜를 `YYYY-MM-DD`로 (최근 메인 차트와 동일)
3. **매수/매도 마커**: 거래내역을 차트에 마커로 표시
4. **호버 정보박스**: 메인 차트처럼 호버 시 날짜·가격·해당일 거래를 박스로

## 대상 파일

- `frontend/components/holdings/PriceChart.tsx`
- `frontend/lib/chartTime.ts` (신규, `toIsoDateKey` 공유 추출)
- `frontend/components/dashboard/PortfolioChart.tsx` (toIsoDateKey 재export로 기존 테스트 호환)
- `frontend/__tests__/holdings/PriceChart.test.tsx`

## 결정 사항 (사용자 확인됨)

- **현재가**: 시리즈를 오늘까지 연장 (마지막 종가 뒤 오늘·현재가 점 추가, 마지막 값 마커 표시)
- **매수/매도**: 한국식 색 — 매수=빨강 아래 화살표, 매도=파랑 위 화살표 + 수량 라벨('매수 10')
- **날짜**: ISO + 호버 정보박스
- **Codex**: 설계·리뷰 참여

## 데이터

`HoldingDetail`: `snapshots`(Snapshot[]: snapshot_date, close_price), `current_price`(string|null),
`transactions`(Transaction[]: type 'buy'|'sell', quantity, price, transaction_date), `currency`.

## 컴포넌트 / 데이터 흐름

### 1. 현재가까지 시리즈 연장 (순수 함수)

`buildPricePoints(snapshots, currentPrice, todayKey)` → `{ time, value }[]`

- 종가 점 생성: `snapshots.map(s => ({ time: s.snapshot_date, value: parseFloat(s.close_price) }))` (오름차순 보장).
- `currentPrice` 파싱 가능 시:
  - `todayKey > 마지막 종가일` → `{ time: todayKey, value: currentPrice }` 추가
  - `todayKey === 마지막 종가일` → 마지막 점 값을 `currentPrice`로 덮어씀
  - `todayKey < 마지막 종가일`(이례적) → 덮어쓰지 않음(마지막 점 유지)
- `currentPrice` null/비숫자면 연장 없음.
- `todayKey`는 컴포넌트에서 `new Date()` 기준 로컬 `YYYY-MM-DD`로 계산해 주입(순수 함수는 결정적).
- area 시리즈 `priceLineVisible: true` → 마지막 값(현재가)이 수평 기준선으로도 표시됨.

### 2. 매수/매도 마커 (순수 함수)

`buildTransactionMarkers(transactions, range)` → `SeriesMarker<Time>[]`

- 매수(`type==='buy'`): `position:'belowBar'`, `shape:'arrowUp'`, `color:'#dc2626'`, `text:'매수 {수량}'`
- 매도(`type==='sell'`): `position:'aboveBar'`, `shape:'arrowDown'`, `color:'#2563eb'`, `text:'매도 {수량}'`
- 수량 포맷: 불필요한 소수점 제거(`formatMarkerQuantity`).
- `transaction_date` 오름차순 정렬(lightweight-charts 요구).
- `range = { from, to }`(시리즈 첫 점 ~ 마지막 점 날짜) 밖 거래는 제외(마커 렌더 오류 방지).
- 적용: `areaSeries.setMarkers(markers)`.

### 3. ISO 날짜 + 호버 정보박스

- `createChart` 옵션에 `localization.dateFormat: 'yyyy-MM-dd'` 추가(기존 priceFormatter 유지).
- `buildPriceTooltipData(snapshots, transactions, currentPrice, todayKey)` → `Map<dateKey, { price, txs }>`
  - `price`: 해당 날짜의 종가(연장된 오늘 키는 currentPrice).
  - `txs`: 해당 날짜 거래 배열(type, quantity, price).
- 호버: `chart.subscribeCrosshairMove(handler)` — 메인 차트와 동일 패턴.
  - 부모 `position:relative`, 자식 absolute div(tooltipRef), imperative 갱신.
  - `toIsoDateKey(param.time)`로 키 변환, Map 조회, `param.point` 기준 위치 + 경계 클램핑, 비활성 시 숨김.
  - 박스 내용: 날짜 / 가격 / 해당일 거래(있으면 '매수 N @가격', '매도 N @가격').

### 4. 공유 헬퍼

`toIsoDateKey`를 `PortfolioChart`에서 `lib/chartTime.ts`로 이동(문자열/BusinessDay→ISO 가드).
`PortfolioChart`는 `export { toIsoDateKey } from '@/lib/chartTime'`로 재export → 기존 import·테스트 호환.

### 5. Cleanup

- teardown에 `chart.unsubscribeCrosshairMove(handler)` 추가(기존 resize 정리·`chart.remove()`와 함께).
- 툴팁 div는 JSX로 렌더되어 React가 정리.

## 에러 처리

- `snapshots` 비어 있음 → 기존 안내 메시지 유지.
- `current_price` null/비숫자 → 연장·마지막 마커 생략.
- 거래 없음 → 마커 없음.
- 시리즈 범위 밖 거래 → 마커 제외.
- 알 수 없는 `param.time` → 툴팁 숨김.

## 테스트 전략 (TDD)

`PriceChart`는 lightweight-charts를 동적 import → 순수 함수 추출 후 단위 테스트:

1. `buildPricePoints` — 연장 / 덮어쓰기(today==last) / null currentPrice / 빈 snapshots.
2. `buildTransactionMarkers` — 매수·매도 색·모양·position·텍스트, 수량 포맷, 정렬, 범위 필터.
3. `buildPriceTooltipData` — 날짜→가격·거래 매핑, 오늘 키 currentPrice.
4. 통합 — createChart 옵션 dateFormat, `setMarkers` 호출, `subscribeCrosshairMove`/`unsubscribeCrosshairMove` 구독·정리.

기존 `__tests__/holdings/PriceChart.test.tsx` mock 패턴 준수(필요 시 `setMarkers`/`subscribeCrosshairMove` mock 추가).

## 리뷰

구현 후 Codex 리뷰 받아 함께 검토.
