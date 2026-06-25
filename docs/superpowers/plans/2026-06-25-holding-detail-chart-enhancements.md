# 종목 상세 차트 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 상세 차트에 현재가까지 시리즈 연장, ISO 날짜, 매수/매도 마커, 호버 정보박스를 추가한다.

**Architecture:** 지표/마커/툴팁 계산을 순수 함수(`buildPricePoints`, `buildTransactionMarkers`, `buildPriceTooltipData`, `formatMarkerQuantity`)로 추출해 단위 테스트하고, `PriceChart`는 시리즈 연장·`setMarkers`·`localization.dateFormat`·`subscribeCrosshairMove` 툴팁을 적용한다. 날짜 키 변환 `toIsoDateKey`는 `lib/chartTime.ts`로 공유 추출한다.

**Tech Stack:** Next.js 14, TypeScript, lightweight-charts v4.2.3, Jest + Testing Library

---

## File Structure

- Create: `frontend/lib/chartTime.ts` — `toIsoDateKey` 공유 헬퍼
- Modify: `frontend/components/dashboard/PortfolioChart.tsx` — 로컬 `toIsoDateKey` 제거, `lib/chartTime`에서 import + 재export
- Modify: `frontend/components/holdings/PriceChart.tsx` — 순수 함수 export + 차트 통합(props 추가)
- Modify: `frontend/app/holdings/[id]/page.tsx` — `currentPrice`/`transactions` props 전달
- Modify: `frontend/__tests__/holdings/PriceChart.test.tsx` — 순수 함수 + 통합 테스트

---

## Task 1: `toIsoDateKey` 공유 추출

**Files:**
- Create: `frontend/lib/chartTime.ts`
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`

- [ ] **Step 1: Create `lib/chartTime.ts`**

```ts
export function toIsoDateKey(time: unknown): string | null {
  if (typeof time === 'string') return time
  if (
    time !== null
    && typeof time === 'object'
    && 'year' in time
    && 'month' in time
    && 'day' in time
  ) {
    const { year, month, day } = time as { year: number; month: number; day: number }
    return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  }
  return null
}
```

- [ ] **Step 2: Replace the local definition in `PortfolioChart.tsx`**

Remove the existing `export function toIsoDateKey(...) { ... }` block (the whole function). Add near the top imports:

```ts
import { toIsoDateKey } from '@/lib/chartTime'
```

And re-export so existing imports/tests keep working — add after the imports:

```ts
export { toIsoDateKey }
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `cd frontend && npx jest PortfolioChartTooltip PortfolioChartLegend`
Expected: PASS (toIsoDateKey tests still pass via re-export)

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/chartTime.ts frontend/components/dashboard/PortfolioChart.tsx
git commit -m "refactor: extract toIsoDateKey to shared lib/chartTime"
```

---

## Task 2: `buildPricePoints` — 현재가까지 연장

**Files:**
- Modify: `frontend/components/holdings/PriceChart.tsx`
- Test: `frontend/__tests__/holdings/PriceChart.test.tsx`

- [ ] **Step 1: Write the failing test**

`PriceChart.test.tsx` 상단(기존 `snapshots` 아래)에 추가. 먼저 import 확장:

```tsx
import { PriceChart, buildPricePoints } from '@/components/holdings/PriceChart'
import type { Snapshot } from '@/lib/types'
```

describe 추가:

```tsx
const priceSnaps: Snapshot[] = [
  { snapshot_date: '2026-06-01', close_price: '100', total_value: '0' },
  { snapshot_date: '2026-06-02', close_price: '110', total_value: '0' },
]

describe('buildPricePoints', () => {
  it('appends today + current price when today is after the last snapshot', () => {
    expect(buildPricePoints(priceSnaps, '120', '2026-06-03')).toEqual([
      { time: '2026-06-01', value: 100 },
      { time: '2026-06-02', value: 110 },
      { time: '2026-06-03', value: 120 },
    ])
  })

  it('overrides the last point value when today equals the last snapshot', () => {
    expect(buildPricePoints(priceSnaps, '115', '2026-06-02')).toEqual([
      { time: '2026-06-01', value: 100 },
      { time: '2026-06-02', value: 115 },
    ])
  })

  it('leaves points unchanged when current price is null or not numeric', () => {
    expect(buildPricePoints(priceSnaps, null, '2026-06-03')).toEqual([
      { time: '2026-06-01', value: 100 },
      { time: '2026-06-02', value: 110 },
    ])
  })

  it('returns empty for empty snapshots', () => {
    expect(buildPricePoints([], '120', '2026-06-03')).toEqual([])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx jest PriceChart -t buildPricePoints`
Expected: FAIL — `buildPricePoints is not a function`

- [ ] **Step 3: Write minimal implementation**

`PriceChart.tsx`에 추가 (컴포넌트 위, export):

```ts
import type { Snapshot, Transaction } from '@/lib/types'

export interface PricePoint {
  time: string
  value: number
}

export function buildPricePoints(
  snapshots: Snapshot[],
  currentPrice: string | null,
  todayKey: string,
): PricePoint[] {
  const points = snapshots
    .map((s) => ({ time: s.snapshot_date, value: parseFloat(s.close_price) }))
    .filter((p) => Number.isFinite(p.value))
    .sort((a, b) => a.time.localeCompare(b.time))
  const cp = currentPrice === null ? NaN : Number(currentPrice)
  if (!Number.isFinite(cp) || points.length === 0) return points
  const last = points[points.length - 1]
  if (todayKey > last.time) return [...points, { time: todayKey, value: cp }]
  if (todayKey === last.time) return [...points.slice(0, -1), { time: last.time, value: cp }]
  return points
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx jest PriceChart -t buildPricePoints`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/components/holdings/PriceChart.tsx frontend/__tests__/holdings/PriceChart.test.tsx
git commit -m "feat: add buildPricePoints to extend price series to current price"
```

---

## Task 3: `formatMarkerQuantity` + `buildTransactionMarkers`

**Files:**
- Modify: `frontend/components/holdings/PriceChart.tsx`
- Test: `frontend/__tests__/holdings/PriceChart.test.tsx`

- [ ] **Step 1: Write the failing test**

import 확장 + describe 추가:

```tsx
import {
  PriceChart,
  buildPricePoints,
  buildTransactionMarkers,
} from '@/components/holdings/PriceChart'
import type { Snapshot, Transaction } from '@/lib/types'

const tx = (over: Partial<Transaction>): Transaction => ({
  id: 't', type: 'BUY', quantity: '10', price: '100',
  transaction_date: '2026-06-01', principal_flow: 'IN',
  created_at: '2026-06-01T00:00:00Z', source_group_id: null,
  label_ids: [], requires_review: false, buy_lot: null, sell_allocations: [],
  ...over,
})

describe('buildTransactionMarkers', () => {
  it('maps buy/sell to Korean-colored arrows with quantity labels, sorted by date', () => {
    const markers = buildTransactionMarkers([
      tx({ type: 'SELL', quantity: '5', transaction_date: '2026-06-03' }),
      tx({ type: 'BUY', quantity: '10', transaction_date: '2026-06-01' }),
    ], { from: '2026-06-01', to: '2026-06-03' })
    expect(markers).toEqual([
      { time: '2026-06-01', position: 'belowBar', shape: 'arrowUp', color: '#dc2626', text: '매수 10' },
      { time: '2026-06-03', position: 'aboveBar', shape: 'arrowDown', color: '#2563eb', text: '매도 5' },
    ])
  })

  it('drops trailing zeros in quantity and excludes out-of-range dates', () => {
    const markers = buildTransactionMarkers([
      tx({ quantity: '0.500', transaction_date: '2026-06-02' }),
      tx({ quantity: '10', transaction_date: '2026-05-01' }),
    ], { from: '2026-06-01', to: '2026-06-03' })
    expect(markers).toEqual([
      { time: '2026-06-02', position: 'belowBar', shape: 'arrowUp', color: '#dc2626', text: '매수 0.5' },
    ])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx jest PriceChart -t buildTransactionMarkers`
Expected: FAIL — `buildTransactionMarkers is not a function`

- [ ] **Step 3: Write minimal implementation**

```ts
export interface PriceMarker {
  time: string
  position: 'aboveBar' | 'belowBar'
  shape: 'arrowUp' | 'arrowDown'
  color: string
  text: string
}

export function formatMarkerQuantity(quantity: string): string {
  const n = Number(quantity)
  return Number.isFinite(n) ? String(n) : quantity
}

export function buildTransactionMarkers(
  transactions: Transaction[],
  range: { from: string; to: string } | null,
): PriceMarker[] {
  const inRange = (date: string) => !range || (date >= range.from && date <= range.to)
  return transactions
    .filter((t) => inRange(t.transaction_date))
    .slice()
    .sort((a, b) => a.transaction_date.localeCompare(b.transaction_date))
    .map((t) => (t.type === 'BUY'
      ? {
        time: t.transaction_date, position: 'belowBar' as const, shape: 'arrowUp' as const,
        color: '#dc2626', text: `매수 ${formatMarkerQuantity(t.quantity)}`,
      }
      : {
        time: t.transaction_date, position: 'aboveBar' as const, shape: 'arrowDown' as const,
        color: '#2563eb', text: `매도 ${formatMarkerQuantity(t.quantity)}`,
      }))
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx jest PriceChart -t buildTransactionMarkers`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/components/holdings/PriceChart.tsx frontend/__tests__/holdings/PriceChart.test.tsx
git commit -m "feat: add buildTransactionMarkers for buy/sell chart markers"
```

---

## Task 4: `buildPriceTooltipData`

**Files:**
- Modify: `frontend/components/holdings/PriceChart.tsx`
- Test: `frontend/__tests__/holdings/PriceChart.test.tsx`

- [ ] **Step 1: Write the failing test**

import에 `buildPriceTooltipData` 추가, describe 추가:

```tsx
describe('buildPriceTooltipData', () => {
  it('maps each date to its price and same-day transactions', () => {
    const map = buildPriceTooltipData(
      priceSnaps,
      [tx({ type: 'BUY', quantity: '10', price: '100', transaction_date: '2026-06-01' })],
      '120',
      '2026-06-03',
    )
    expect(map.get('2026-06-01')).toEqual({
      date: '2026-06-01', price: 100,
      txs: [{ type: 'BUY', quantity: '10', price: '100' }],
    })
    expect(map.get('2026-06-03')).toEqual({ date: '2026-06-03', price: 120, txs: [] })
  })

  it('includes transaction-only dates with a null price', () => {
    const map = buildPriceTooltipData(
      priceSnaps,
      [tx({ type: 'SELL', quantity: '2', price: '130', transaction_date: '2026-05-20' })],
      null,
      '2026-06-03',
    )
    expect(map.get('2026-05-20')).toEqual({
      date: '2026-05-20', price: null,
      txs: [{ type: 'SELL', quantity: '2', price: '130' }],
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx jest PriceChart -t buildPriceTooltipData`
Expected: FAIL — `buildPriceTooltipData is not a function`

- [ ] **Step 3: Write minimal implementation**

```ts
export interface PriceTxInfo {
  type: Transaction['type']
  quantity: string
  price: string
}

export interface PriceTooltipDatum {
  date: string
  price: number | null
  txs: PriceTxInfo[]
}

export function buildPriceTooltipData(
  snapshots: Snapshot[],
  transactions: Transaction[],
  currentPrice: string | null,
  todayKey: string,
): Map<string, PriceTooltipDatum> {
  const map = new Map<string, PriceTooltipDatum>()
  for (const point of buildPricePoints(snapshots, currentPrice, todayKey)) {
    map.set(point.time, { date: point.time, price: point.value, txs: [] })
  }
  for (const t of transactions) {
    const entry = map.get(t.transaction_date)
      ?? { date: t.transaction_date, price: null, txs: [] }
    entry.txs.push({ type: t.type, quantity: t.quantity, price: t.price })
    map.set(t.transaction_date, entry)
  }
  return map
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx jest PriceChart -t buildPriceTooltipData`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/components/holdings/PriceChart.tsx frontend/__tests__/holdings/PriceChart.test.tsx
git commit -m "feat: add buildPriceTooltipData for price chart hover box"
```

---

## Task 5: 차트 통합 — props · 시리즈 연장 · 마커 · ISO 날짜 · 호버 툴팁

**Files:**
- Modify: `frontend/components/holdings/PriceChart.tsx`
- Modify: `frontend/app/holdings/[id]/page.tsx`
- Modify: `frontend/__tests__/holdings/PriceChart.test.tsx`

- [ ] **Step 1: Extend the test mock + add integration test**

`PriceChart.test.tsx`의 `createChart` mock을 확장:

```tsx
const setData = jest.fn()
const setMarkers = jest.fn()
const subscribeCrosshairMove = jest.fn()
const unsubscribeCrosshairMove = jest.fn()
const createChart = jest.fn(() => ({
  addAreaSeries: jest.fn(() => ({ setData, setMarkers })),
  timeScale: jest.fn(() => ({ fitContent })),
  subscribeCrosshairMove,
  unsubscribeCrosshairMove,
  applyOptions,
  remove,
}))
```

기존 `creates only one chart instance` 테스트의 `setData` 단언은 유지(현재가 없으면 종가만). 통합 테스트 추가:

```tsx
it('configures ISO dates, draws markers, and subscribes the crosshair with cleanup', async () => {
  const { unmount } = render(
    <PriceChart
      snapshots={snapshots}
      currency="KRW"
      currentPrice={null}
      transactions={[{
        id: 't1', type: 'BUY', quantity: '10', price: '100',
        transaction_date: '2026-06-01', principal_flow: 'IN',
        created_at: '2026-06-01T00:00:00Z', source_group_id: null,
        label_ids: [], requires_review: false, buy_lot: null, sell_allocations: [],
      }]}
    />,
  )

  await waitFor(() => expect(createChart).toHaveBeenCalledTimes(1))
  expect(createChart.mock.calls[0][0].localization.dateFormat).toBe('yyyy-MM-dd')
  expect(setMarkers).toHaveBeenCalledWith([
    { time: '2026-06-01', position: 'belowBar', shape: 'arrowUp', color: '#dc2626', text: '매수 10' },
  ])
  await waitFor(() => expect(subscribeCrosshairMove).toHaveBeenCalledTimes(1))
  const handler = subscribeCrosshairMove.mock.calls[0][0]
  unmount()
  expect(unsubscribeCrosshairMove).toHaveBeenCalledWith(handler)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx jest PriceChart -t "configures ISO dates"`
Expected: FAIL — `localization.dateFormat` undefined / `setMarkers` 미호출 / props 타입 오류

- [ ] **Step 3: Update `PriceChart` props + imports**

`Props` 인터페이스를 교체:

```tsx
interface Props {
  snapshots: Snapshot[]
  currency: 'KRW' | 'USD'
  currentPrice: string | null
  transactions: Transaction[]
}

export function PriceChart({ snapshots, currency, currentPrice, transactions }: Props) {
```

`useRef` 옆에 툴팁 ref 추가:

```tsx
  const containerRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
```

- [ ] **Step 4: Build points/markers/tooltip data + apply in the effect**

`useEffect` 내부, `import('lightweight-charts').then(({ createChart, ColorType }) => {` 콜백 안에서:

(a) `createChart` 옵션의 `localization`에 `dateFormat` 추가 — 기존:

```tsx
        localization: {
          priceFormatter: (price: number) => {
```

를 다음으로 교체:

```tsx
        localization: {
          dateFormat: 'yyyy-MM-dd',
          priceFormatter: (price: number) => {
```

(b) `areaSeries.setData(...)` 블록을 점/마커 적용으로 교체. 기존:

```tsx
      areaSeries.setData(
        snapshots.map((s) => ({
          time: s.snapshot_date as import('lightweight-charts').Time,
          value: parseFloat(s.close_price),
        })),
      )

      chart.timeScale().fitContent()
```

를 다음으로 교체:

```tsx
      const todayKey = toLocalDateKey(new Date())
      const points = buildPricePoints(snapshots, currentPrice, todayKey)
      areaSeries.setData(points.map((p) => ({
        time: p.time as import('lightweight-charts').Time,
        value: p.value,
      })))

      const range = points.length > 0
        ? { from: points[0].time, to: points[points.length - 1].time }
        : null
      const markers = buildTransactionMarkers(transactions, range)
      areaSeries.setMarkers(markers as Parameters<typeof areaSeries.setMarkers>[0])

      const tooltipData = buildPriceTooltipData(snapshots, transactions, currentPrice, todayKey)
      const tooltipEl = tooltipRef.current
      crosshairHandler = (param) => {
        if (!tooltipEl) return
        const key = param.time !== undefined ? toIsoDateKey(param.time) : null
        const datum = key ? tooltipData.get(key) : undefined
        if (!param.point || !datum) {
          tooltipEl.style.display = 'none'
          return
        }
        const priceText = datum.price === null ? '-' : formatPrice(datum.price)
        const txRows = datum.txs.map((t) => {
          const label = t.type === 'BUY' ? '매수' : '매도'
          const color = t.type === 'BUY' ? '#dc2626' : '#2563eb'
          return `<div class="flex justify-between gap-4"><span style="color:${color}">${label} ${formatMarkerQuantity(t.quantity)}</span><span class="text-gray-500">@${formatPrice(parseFloat(t.price))}</span></div>`
        }).join('')
        tooltipEl.innerHTML = [
          `<div class="mb-1 font-semibold text-gray-700">${datum.date}</div>`,
          `<div class="flex justify-between gap-4"><span class="text-gray-500">가격</span><span class="font-medium text-gray-800">${priceText}</span></div>`,
          txRows,
        ].join('')
        tooltipEl.style.display = 'block'
        const boxWidth = tooltipEl.offsetWidth
        const margin = 12
        const width = containerRef.current?.clientWidth ?? 0
        let left = param.point.x + margin
        if (left + boxWidth > width) left = param.point.x - boxWidth - margin
        if (left < 0) left = 0
        let top = param.point.y + margin
        if (top + tooltipEl.offsetHeight > 280) top = param.point.y - tooltipEl.offsetHeight - margin
        if (top < 0) top = 0
        tooltipEl.style.left = `${left}px`
        tooltipEl.style.top = `${top}px`
      }
      chart.subscribeCrosshairMove(crosshairHandler)

      chart.timeScale().fitContent()
```

(c) effect 상단(`let handleResize` 옆)에 핸들러 변수 + 가격 포맷 헬퍼 선언:

```tsx
    let handleResize: (() => void) | null = null
    let crosshairHandler: import('lightweight-charts').MouseEventHandler<import('lightweight-charts').Time> | null = null
    const formatPrice = (price: number) =>
      currency === 'KRW' ? `₩${Math.round(price).toLocaleString('ko-KR')}` : `$${price.toFixed(2)}`
```

그리고 `createChart` 옵션의 `priceFormatter`를 `formatPrice` 재사용으로 단순화(선택) — 기존 인라인 유지해도 무방하니 변경하지 않아도 됨.

- [ ] **Step 5: Cleanup + 모듈 상단 헬퍼 + imports**

파일 상단 import 교체:

```tsx
import { useEffect, useRef } from 'react'
import type { Snapshot, Transaction } from '@/lib/types'
import { toIsoDateKey } from '@/lib/chartTime'
```

모듈 하단(또는 buildPricePoints 근처)에 로컬 날짜 키 헬퍼 추가:

```ts
function toLocalDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
```

teardown에 crosshair 해제 추가 — 기존:

```tsx
    return () => {
      cancelled = true
      if (handleResize) window.removeEventListener('resize', handleResize)
      chart?.remove()
    }
```

를:

```tsx
    return () => {
      cancelled = true
      if (handleResize) window.removeEventListener('resize', handleResize)
      if (chart && crosshairHandler) chart.unsubscribeCrosshairMove(crosshairHandler)
      chart?.remove()
    }
```

effect 의존성 배열에 `currentPrice`, `transactions` 추가:

```tsx
  }, [snapshots, currency, currentPrice, transactions])
```

JSX 반환부에 relative 래퍼 + 툴팁 div. 기존:

```tsx
  return <div ref={containerRef} className="w-full" />
```

를:

```tsx
  return (
    <div className="relative w-full">
      <div ref={containerRef} className="w-full" />
      <div
        ref={tooltipRef}
        className="pointer-events-none absolute left-0 top-0 z-10 hidden min-w-[160px] rounded-md border border-gray-200 bg-white px-3 py-2 text-xs shadow-lg"
      />
    </div>
  )
```

- [ ] **Step 6: Pass new props from the detail page**

`app/holdings/[id]/page.tsx`의 PriceChart 호출 — 기존:

```tsx
        <PriceChart snapshots={holding.snapshots} currency={holding.currency} />
```

를:

```tsx
        <PriceChart
          snapshots={holding.snapshots}
          currency={holding.currency}
          currentPrice={holding.current_price}
          transactions={holding.transactions}
        />
```

- [ ] **Step 7: Run tests + typecheck + build**

Run: `cd frontend && npx jest PriceChart`
Expected: PASS (순수 함수 + 통합 + 기존 StrictMode 테스트)

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -E "PriceChart.tsx|holdings/\[id\]/page.tsx|chartTime" | grep -v test | wc -l`
Expected: `0`

- [ ] **Step 8: Commit**

```bash
git add frontend/components/holdings/PriceChart.tsx frontend/app/holdings/[id]/page.tsx frontend/__tests__/holdings/PriceChart.test.tsx
git commit -m "feat: add current price, ISO dates, buy/sell markers, hover box to holding chart"
```

---

## Task 6: 브라우저 검증

- [ ] **Step 1**: dev 서버 기동, 종목 상세 페이지로 이동(로그인 상태).
- [ ] **Step 2**: 라인이 현재가까지 이어지는지, 마지막 값/priceLine이 현재가인지 확인.
- [ ] **Step 3**: 매수(빨강 ↑)·매도(파랑 ↓) 마커 + 수량 라벨이 거래일에 표시되는지 확인.
- [ ] **Step 4**: 크로스헤어 날짜가 `YYYY-MM-DD`인지, 호버 박스에 날짜·가격·해당일 거래가 뜨는지 확인.
- [ ] **Step 5**: 콘솔 에러 없음 확인, 스크린샷 공유.

---

## Self-Review (작성자 확인 완료)

- **Spec coverage**: 현재가 연장(Task 2·5), 매수/매도 마커(Task 3·5), ISO 날짜(Task 5), 호버 박스(Task 4·5), toIsoDateKey 공유(Task 1) 모두 매핑됨.
- **Placeholder scan**: 모든 코드 스텝 실제 코드 포함, TBD 없음.
- **Type consistency**: `PricePoint`/`PriceMarker`/`PriceTooltipDatum`/`PriceTxInfo` 및 `buildPricePoints`/`buildTransactionMarkers`/`buildPriceTooltipData`/`formatMarkerQuantity`/`toLocalDateKey`/`toIsoDateKey` 시그니처가 태스크 간 일치. `TxType`='BUY'|'SELL' 확인됨.
