# 포트폴리오 차트 호버 툴팁 + ISO 날짜 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드 평가금액 차트에 마우스 오버 시 해당 날짜의 5개 지표(평가금액·총손익·총손익율·일별손익·투자원금/잔여원금)를 박스로 표시하고, 크로스헤어 날짜 라벨을 `YYYY-MM-DD`로 표시한다.

**Architecture:** 지표 계산과 날짜 키 변환을 순수 함수(`buildTooltipData`, `toIsoDateKey`, `formatTooltipPercent`)로 추출해 단위 테스트한다. `DashboardPortfolioChart`는 메인 차트에 `subscribeCrosshairMove`를 구독해 imperative DOM으로 절대위치 툴팁을 갱신하고, `createChart`에 `localization.dateFormat: 'yyyy-MM-dd'`를 추가한다.

**Tech Stack:** Next.js 14, TypeScript, TradingView Lightweight Charts v4, Jest + Testing Library

---

## File Structure

- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
  - 신규 export 순수 함수: `toIsoDateKey`, `buildTooltipData`, `formatTooltipPercent`, 타입 `TooltipDatum`
  - `DashboardPortfolioChart`에 툴팁 DOM(JSX wrapper + ref) · 크로스헤어 구독 · `localization.dateFormat` 추가
- Create/Modify test: `frontend/__tests__/dashboard/PortfolioChartTooltip.test.tsx` (순수 함수 단위 테스트)
- Modify test: `frontend/__tests__/dashboard/PortfolioChartLegend.test.tsx` (createChart 모크에 `subscribeCrosshairMove`/`unsubscribeCrosshairMove` 추가 — 통합 검증용)

---

## Task 1: `toIsoDateKey` — 크로스헤어 time → ISO 키 변환

**Files:**
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Test: `frontend/__tests__/dashboard/PortfolioChartTooltip.test.tsx`

- [ ] **Step 1: Write the failing test**

`frontend/__tests__/dashboard/PortfolioChartTooltip.test.tsx` 생성:

```tsx
import { toIsoDateKey } from '@/components/dashboard/PortfolioChart'

describe('toIsoDateKey', () => {
  it('returns ISO string inputs unchanged', () => {
    expect(toIsoDateKey('2026-06-25')).toBe('2026-06-25')
  })

  it('formats a BusinessDay object with zero padding', () => {
    expect(toIsoDateKey({ year: 2026, month: 6, day: 5 })).toBe('2026-06-05')
  })

  it('returns null for unsupported time shapes', () => {
    expect(toIsoDateKey(1750000000 as unknown)).toBeNull()
    expect(toIsoDateKey(undefined)).toBeNull()
    expect(toIsoDateKey(null)).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- PortfolioChartTooltip`
Expected: FAIL — `toIsoDateKey is not a function` / 모듈에 export 없음

- [ ] **Step 3: Write minimal implementation**

`PortfolioChart.tsx`에 추가 (`parseNullableNumber` 근처, export):

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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- PortfolioChartTooltip`
Expected: PASS (toIsoDateKey 3 케이스)

- [ ] **Step 5: Commit**

```bash
git add frontend/components/dashboard/PortfolioChart.tsx frontend/__tests__/dashboard/PortfolioChartTooltip.test.tsx
git commit -m "feat: add toIsoDateKey for crosshair date key matching"
```

---

## Task 2: `formatTooltipPercent` — 총손익율 포맷

**Files:**
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Test: `frontend/__tests__/dashboard/PortfolioChartTooltip.test.tsx`

- [ ] **Step 1: Write the failing test**

위 테스트 파일에 describe 추가:

```tsx
import { toIsoDateKey, formatTooltipPercent } from '@/components/dashboard/PortfolioChart'

describe('formatTooltipPercent', () => {
  it('formats with two decimals and percent sign', () => {
    expect(formatTooltipPercent(8.333)).toBe('8.33%')
  })

  it('keeps the minus sign for losses', () => {
    expect(formatTooltipPercent(-4.5)).toBe('-4.50%')
  })

  it('returns a dash for null', () => {
    expect(formatTooltipPercent(null)).toBe('-')
  })
})
```

(기존 `import { toIsoDateKey } ...` 줄을 위 줄로 교체)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- PortfolioChartTooltip`
Expected: FAIL — `formatTooltipPercent is not a function`

- [ ] **Step 3: Write minimal implementation**

```ts
export function formatTooltipPercent(value: number | null): string {
  if (value === null) return '-'
  return `${value.toFixed(2)}%`
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- PortfolioChartTooltip`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/components/dashboard/PortfolioChart.tsx frontend/__tests__/dashboard/PortfolioChartTooltip.test.tsx
git commit -m "feat: add formatTooltipPercent helper"
```

---

## Task 3: `buildTooltipData` — 날짜별 지표 맵

**Files:**
- Modify: `frontend/components/dashboard/PortfolioChart.tsx`
- Test: `frontend/__tests__/dashboard/PortfolioChartTooltip.test.tsx`

- [ ] **Step 1: Write the failing test**

테스트 파일 상단 import를 확장하고 describe 추가:

```tsx
import {
  toIsoDateKey,
  formatTooltipPercent,
  buildTooltipData,
} from '@/components/dashboard/PortfolioChart'
import type { DashboardHistoryRow } from '@/lib/types'

const rows: DashboardHistoryRow[] = [
  {
    group_kind: 'total', group_id: null, group_name: '전체',
    snapshot_date: '2026-06-01',
    total_value: '750000', total_invested_principal: '600000',
    total_cost_basis: '700000', total_profit_loss: '50000',
  },
  {
    group_kind: 'total', group_id: null, group_name: '전체',
    snapshot_date: '2026-06-02',
    total_value: '760000', total_invested_principal: '600000',
    total_cost_basis: '700000', total_profit_loss: '60000',
  },
]

const dailyProfitChange = [
  { time: '2026-06-01' },
  { time: '2026-06-02', value: 10000, color: '#dc2626' },
]

describe('buildTooltipData', () => {
  it('builds per-date metrics keyed by ISO date with invested-principal base', () => {
    const map = buildTooltipData(rows, dailyProfitChange, 'invested')
    const day2 = map.get('2026-06-02')
    expect(day2).toEqual({
      date: '2026-06-02',
      value: 760000,
      profit: 60000,
      rate: 10, // 60000 / 600000 * 100
      daily: 10000,
      principal: 600000,
      principalLabel: '투자원금',
    })
  })

  it('uses cost basis and 잔여원금 label when referenceField is cost', () => {
    const map = buildTooltipData(rows, dailyProfitChange, 'cost')
    const day2 = map.get('2026-06-02')
    expect(day2?.principal).toBe(700000)
    expect(day2?.principalLabel).toBe('잔여원금')
    expect(day2?.rate).toBeCloseTo((60000 / 700000) * 100, 6)
  })

  it('returns null daily for whitespace dates and null rate when principal is 0', () => {
    const zeroRows: DashboardHistoryRow[] = [{
      group_kind: 'total', group_id: null, group_name: '전체',
      snapshot_date: '2026-06-01',
      total_value: '750000', total_invested_principal: '0',
      total_cost_basis: '700000', total_profit_loss: '50000',
    }]
    const map = buildTooltipData(zeroRows, [{ time: '2026-06-01' }], 'invested')
    const day1 = map.get('2026-06-01')
    expect(day1?.daily).toBeNull()
    expect(day1?.rate).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- PortfolioChartTooltip`
Expected: FAIL — `buildTooltipData is not a function`

- [ ] **Step 3: Write minimal implementation**

`PortfolioChart.tsx`에 추가 (타입 + 함수). `referenceRowField`, `referenceFieldLabel`, `parseNullableNumber`, `ColoredChartPoint`, `ChartWhitespacePoint`, `ChartReferenceField`는 이미 모듈에 존재하므로 재사용:

```ts
export interface TooltipDatum {
  date: string
  value: number | null
  profit: number | null
  rate: number | null
  daily: number | null
  principal: number | null
  principalLabel: string
}

export function buildTooltipData(
  rows: DashboardHistoryRow[],
  dailyProfitChange: Array<ColoredChartPoint | ChartWhitespacePoint>,
  referenceField: ChartReferenceField,
): Map<string, TooltipDatum> {
  const principalField = referenceRowField[referenceField]
  const label = referenceFieldLabel[referenceField]
  const dailyByDate = new Map<string, number | null>(
    dailyProfitChange.map((point) => [point.time, 'value' in point ? point.value : null]),
  )
  const map = new Map<string, TooltipDatum>()
  for (const row of rows) {
    const profit = parseNullableNumber(row.total_profit_loss)
    const principal = parseNullableNumber(row[principalField])
    const rate = profit !== null && principal !== null && principal !== 0
      ? (profit / principal) * 100
      : null
    map.set(row.snapshot_date, {
      date: row.snapshot_date,
      value: parseNullableNumber(row.total_value),
      profit,
      rate,
      daily: dailyByDate.has(row.snapshot_date) ? dailyByDate.get(row.snapshot_date)! : null,
      principal,
      principalLabel: label,
    })
  }
  return map
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- PortfolioChartTooltip`
Expected: PASS (buildTooltipData 3 케이스 + 이전 태스크 케이스)

- [ ] **Step 5: Commit**

```bash
git add frontend/components/dashboard/PortfolioChart.tsx frontend/__tests__/dashboard/PortfolioChartTooltip.test.tsx
git commit -m "feat: add buildTooltipData for per-date chart tooltip metrics"
```

---

## Task 4: 차트 통합 — 툴팁 DOM · 크로스헤어 구독 · ISO 날짜 라벨

**Files:**
- Modify: `frontend/components/dashboard/PortfolioChart.tsx` (`DashboardPortfolioChart`)
- Modify: `frontend/__tests__/dashboard/PortfolioChartLegend.test.tsx` (모크 확장)

- [ ] **Step 1: createChart 모크에 crosshair 메서드 추가 + dateFormat 검증 테스트**

`PortfolioChartLegend.test.tsx`의 `createChart` 모크 반환 객체에 추가:

```tsx
    subscribeCrosshairMove: jest.fn(),
    unsubscribeCrosshairMove: jest.fn(),
```

같은 파일에 테스트 추가:

```tsx
  it('configures ISO date labels and a crosshair subscription with cleanup', async () => {
    const { unmount } = render(
      <PortfolioChart
        historyRows={totalRows}
        compositionRows={totalRows}
        includeComposition
        displayCurrency="KRW"
        visibleRange={null}
      />,
    )

    await waitFor(() => {
      expect(createChart).toHaveBeenCalledTimes(2)
    })
    expect(createChart.mock.calls[0][1].localization.dateFormat).toBe('yyyy-MM-dd')

    const mainChart = createChart.mock.results[0].value
    await waitFor(() => {
      expect(mainChart.subscribeCrosshairMove).toHaveBeenCalledTimes(1)
    })
    const handler = mainChart.subscribeCrosshairMove.mock.calls[0][0]

    unmount()
    expect(mainChart.unsubscribeCrosshairMove).toHaveBeenCalledWith(handler)
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- PortfolioChartLegend`
Expected: FAIL — `localization.dateFormat` undefined / `subscribeCrosshairMove` 미호출

- [ ] **Step 3: Implement — localization.dateFormat**

`DashboardPortfolioChart`의 `commonLayout` 아래에 공통 localization을 만들어 두 `createChart` 호출의 `localization`에 `dateFormat` 추가. 기존 두 곳:

```ts
        localization: { priceFormatter: formatDashboardMoney },
```

을 각각 다음으로 교체:

```ts
        localization: { priceFormatter: formatDashboardMoney, dateFormat: 'yyyy-MM-dd' },
```

- [ ] **Step 4: Implement — 툴팁 DOM wrapper + ref**

컴포넌트 상단 refs 근처에 추가:

```ts
  const tooltipRef = useRef<HTMLDivElement>(null)
```

`return (...)`의 메인 차트 컨테이너를 relative 부모로 감싸고 툴팁 div 추가. 기존:

```tsx
      <div ref={mainContainerRef} className="w-full" />
```

를 다음으로 교체:

```tsx
      <div className="relative w-full">
        <div ref={mainContainerRef} className="w-full" />
        <div
          ref={tooltipRef}
          className="pointer-events-none absolute left-0 top-0 z-10 hidden min-w-[160px] rounded-md border border-gray-200 bg-white px-3 py-2 text-xs shadow-lg"
        />
      </div>
```

- [ ] **Step 5: Implement — 크로스헤어 구독 + imperative 갱신**

`useEffect` 내부, 차트/시리즈 생성 후(`profitSeries.setData(...)` 이후, 또는 spine 설정 근처) `tooltipData` 맵을 만들고 핸들러를 구독. effect 의존성에 `referenceField` 추가 필요. effect 상단에서:

```ts
    const tooltipData = buildTooltipData(selectedMerge.rows, chartData.dailyProfitChange, referenceField)
```

`import('lightweight-charts').then(...)` 콜백 안, 구독 정리 핸들러 변수 선언부에 추가:

```ts
    let crosshairHandler: import('lightweight-charts').MouseEventHandler<import('lightweight-charts').Time> | null = null
```

`profitSeries.setData(...)` 또는 동기화 구독 이후에:

```ts
      const tooltipEl = tooltipRef.current
      crosshairHandler = (param) => {
        if (!tooltipEl) return
        const key = param.time !== undefined ? toIsoDateKey(param.time) : null
        const datum = key ? tooltipData.get(key) : undefined
        if (!param.point || !datum) {
          tooltipEl.style.display = 'none'
          return
        }
        const profitColor = (v: number | null) =>
          v === null ? '#6b7280' : v >= 0 ? '#dc2626' : '#2563eb'
        const money = (v: number | null) => (v === null ? '-' : formatDashboardMoney(v))
        tooltipEl.innerHTML = [
          `<div class="mb-1 font-semibold text-gray-700">${datum.date}</div>`,
          `<div class="flex justify-between gap-4"><span class="text-gray-500">평가금액</span><span class="font-medium text-gray-800">${money(datum.value)}</span></div>`,
          `<div class="flex justify-between gap-4"><span class="text-gray-500">총손익</span><span class="font-medium" style="color:${profitColor(datum.profit)}">${money(datum.profit)}</span></div>`,
          `<div class="flex justify-between gap-4"><span class="text-gray-500">총손익율</span><span class="font-medium" style="color:${profitColor(datum.rate)}">${formatTooltipPercent(datum.rate)}</span></div>`,
          `<div class="flex justify-between gap-4"><span class="text-gray-500">일별손익</span><span class="font-medium" style="color:${profitColor(datum.daily)}">${money(datum.daily)}</span></div>`,
          `<div class="flex justify-between gap-4"><span class="text-gray-500">${datum.principalLabel}</span><span class="font-medium text-gray-800">${money(datum.principal)}</span></div>`,
        ].join('')
        tooltipEl.style.display = 'block'
        const container = mainContainerRef.current
        const boxWidth = tooltipEl.offsetWidth
        const boxHeight = tooltipEl.offsetHeight
        const margin = 12
        const width = container?.clientWidth ?? 0
        let left = param.point.x + margin
        if (left + boxWidth > width) left = param.point.x - boxWidth - margin
        if (left < 0) left = 0
        let top = param.point.y + margin
        if (top + boxHeight > getDashboardChartLayout().mainHeight) {
          top = param.point.y - boxHeight - margin
        }
        if (top < 0) top = 0
        tooltipEl.style.left = `${left}px`
        tooltipEl.style.top = `${top}px`
      }
      mainChart.subscribeCrosshairMove(crosshairHandler)
```

- [ ] **Step 6: Implement — cleanup**

`useEffect` return(teardown)에 추가 (`mainChart?.remove()` 이전):

```ts
      if (mainChart && crosshairHandler) {
        mainChart.unsubscribeCrosshairMove(crosshairHandler)
      }
```

그리고 effect 의존성 배열에 `referenceField`, `selectedMerge` 추가:

```ts
  }, [chartData, hasData, visibleRange, showGainLossBand, referenceField, selectedMerge])
```

(주의: `crosshairHandler`는 `import().then` 콜백의 클로저 변수이므로, teardown에서 접근 가능하도록 `let crosshairHandler` 선언을 `useEffect` 본문 상단의 다른 `let mainChart` 등과 같은 스코프에 둔다.)

- [ ] **Step 7: Run tests**

Run: `cd frontend && npm test -- PortfolioChartLegend PortfolioChartTooltip`
Expected: PASS (신규 dateFormat/crosshair 테스트 + 기존 회귀 + 순수 함수 테스트 모두 통과)

- [ ] **Step 8: Commit**

```bash
git add frontend/components/dashboard/PortfolioChart.tsx frontend/__tests__/dashboard/PortfolioChartLegend.test.tsx
git commit -m "feat: show hover tooltip with daily metrics and ISO date on portfolio chart"
```

---

## Task 5: 브라우저 검증 (preview)

- [ ] **Step 1**: 프론트 dev 서버 기동 후 대시보드 차트에 마우스 오버.
- [ ] **Step 2**: 툴팁에 5개 지표가 정확히 표시되는지, 토글(투자원금/잔여원금) 전환 시 원금 행 라벨·총손익율 기준이 바뀌는지 확인.
- [ ] **Step 3**: 크로스헤어 날짜 라벨이 `2026-06-25` 순서인지 확인. 축 눈금이 과도하게 길면 `timeScale.tickMarkFormatter` 추가(연/월/일 단위 간결 포맷) 후 재확인.
- [ ] **Step 4**: 콘솔 에러 없음 확인. 스크린샷으로 결과 공유.

---

## Self-Review (작성자 확인 완료)

- **Spec coverage**: 5개 지표(Task 3) · 토글 추종 기준(Task 3) · ISO 날짜(Task 4) · 메인 차트 한정(Task 4) · cleanup(Task 4) · TDD 순수 함수(Task 1-3) 모두 매핑됨.
- **Placeholder scan**: 모든 코드 스텝에 실제 코드 포함. TBD 없음.
- **Type consistency**: `TooltipDatum`/`toIsoDateKey`/`buildTooltipData`/`formatTooltipPercent` 시그니처가 Task 간 일치. `referenceRowField`/`referenceFieldLabel`/`parseNullableNumber`는 기존 모듈 심볼 재사용.
