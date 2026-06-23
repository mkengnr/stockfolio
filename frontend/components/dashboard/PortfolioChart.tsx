'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  Currency,
  DashboardHistoryGroupKind,
  DashboardHistoryRow,
  DashboardSummary,
  DisplayCurrency,
  ScopedPortfolioHistory,
} from '@/lib/types'

type LegacyMeasure = 'value' | 'cost' | 'profit'
type DashboardChartMetric = 'value' | 'principal' | 'profit'
type ChartPoint = { time: string; value: number }
type ColoredChartPoint = ChartPoint & { color: string }
type ChartWhitespacePoint = { time: string }
type CurrencyChartSeries = Record<LegacyMeasure, ChartPoint[]>
type ChartVisibleRange = { from: string; to: string } | null

export interface DashboardBuiltChartSeries {
  id: string
  name: string
  kind: DashboardHistoryGroupKind
  points: ChartPoint[]
}

export interface DashboardLivePoint {
  snapshotDate: string | null
  groupKind: DashboardHistoryGroupKind
  groupId: string | null
  groupName: string
  summary: DashboardSummary
}

type GainLossBandPoint = { time: string; value: number; principal: number }

export interface IntegratedDashboardChartData {
  value: ChartPoint[]
  principal: ChartPoint[]
  dailyProfitChange: Array<ColoredChartPoint | ChartWhitespacePoint>
  gainLossBand: GainLossBandPoint[]
  composition: DashboardBuiltChartSeries[]
}

type LegacyProps = {
  series: ScopedPortfolioHistory['series']
  historyRows?: never
  compositionRows?: never
  includeComposition?: never
  displayCurrency?: never
}

type DashboardProps = {
  historyRows: DashboardHistoryRow[]
  compositionRows: DashboardHistoryRow[]
  includeComposition: boolean
  displayCurrency: DisplayCurrency
  visibleRange: ChartVisibleRange
  showGainLossBand?: boolean
  referenceDefault?: ChartReferenceField | 'auto'
  series?: never
}

type Props = LegacyProps | DashboardProps

const currencies: Currency[] = ['KRW', 'USD']
const legacyMeasures: LegacyMeasure[] = ['value', 'cost', 'profit']

const legacyColors: Record<Currency, Record<LegacyMeasure, string>> = {
  KRW: { value: '#4f46e5', cost: '#a5b4fc', profit: '#818cf8' },
  USD: { value: '#059669', cost: '#a7f3d0', profit: '#34d399' },
}

const dashboardColors = ['#4f46e5', '#059669', '#dc2626', '#d97706', '#7c3aed', '#0891b2', '#be123c']
const dashboardChartRightPadding = 2

const legacyFieldByMeasure = {
  value: 'total_value',
  cost: 'total_invested_principal',
  profit: 'total_profit_loss',
} as const

const dashboardFieldByMetric = {
  value: 'total_value',
  principal: 'total_cost_basis',
  profit: 'total_profit_loss',
} as const

export function buildChartSeries(series: ScopedPortfolioHistory['series']): Record<Currency, CurrencyChartSeries> {
  return Object.fromEntries(currencies.map((currency) => [
    currency,
    Object.fromEntries(legacyMeasures.map((measure) => [
      measure,
      (series[currency] ?? [])
        .filter((point) => point[legacyFieldByMeasure[measure]] !== null)
        .map((point) => ({
          time: point.snapshot_date,
          value: parseFloat(point[legacyFieldByMeasure[measure]]!),
        })),
    ])),
  ])) as Record<Currency, CurrencyChartSeries>
}

export function mergeDashboardLivePoint(
  rows: DashboardHistoryRow[],
  livePoint: DashboardLivePoint | null | undefined,
) {
  if (!livePoint) return { rows, liveDailyProfit: undefined }

  const { snapshotDate, summary } = livePoint
  if (!snapshotDate || summary.total_current_value == null) {
    return { rows, liveDailyProfit: undefined }
  }

  const liveRow: DashboardHistoryRow = {
    group_kind: livePoint.groupKind,
    group_id: livePoint.groupId,
    group_name: livePoint.groupName,
    snapshot_date: snapshotDate,
    total_value: summary.total_current_value,
    total_invested_principal: summary.total_invested_principal,
    total_cost_basis: summary.total_cost_basis,
    total_profit_loss: summary.total_profit_loss,
  }
  const mergedRows = rows
    .filter((row) => !(
      row.snapshot_date === snapshotDate
      && row.group_kind === livePoint.groupKind
      && row.group_id === livePoint.groupId
    ))
    .concat(liveRow)
    .sort((left, right) => left.snapshot_date.localeCompare(right.snapshot_date))

  return {
    rows: mergedRows,
    liveDailyProfit: parseNullableNumber(summary.total_current_value_change),
  }
}

export function buildDashboardChartSeries(
  rows: DashboardHistoryRow[],
  options: { metric: DashboardChartMetric },
): DashboardBuiltChartSeries[] {
  const field = dashboardFieldByMetric[options.metric]
  const grouped = new Map<string, DashboardBuiltChartSeries>()

  for (const row of rows) {
    const id = row.group_kind === 'total' ? 'total:total' : `${row.group_kind}:${row.group_id ?? row.group_kind}`
    const existing = grouped.get(id)
    const series = existing ?? {
      id,
      name: row.group_name,
      kind: row.group_kind,
      points: [],
    }
    const rawValue = row[field]
    if (rawValue !== null) {
      series.points.push({ time: row.snapshot_date, value: parseFloat(rawValue) })
    }
    if (!existing) grouped.set(id, series)
  }

  return Array.from(grouped.values())
    .map((series) => ({
      ...series,
      points: series.points.sort((left, right) => left.time.localeCompare(right.time)),
    }))
    .sort(compareDashboardSeries)
}

export type ChartReferenceField = 'invested' | 'cost'

const referenceRowField: Record<ChartReferenceField, 'total_invested_principal' | 'total_cost_basis'> = {
  invested: 'total_invested_principal',
  cost: 'total_cost_basis',
}

export const referenceFieldLabel: Record<ChartReferenceField, string> = {
  invested: '투자원금',
  cost: '잔여원금',
}

export function buildIntegratedDashboardChartData(
  allRows: DashboardHistoryRow[],
  selectedRows: DashboardHistoryRow[],
  options: {
    includeComposition: boolean
    referenceField?: ChartReferenceField
    liveDailyProfit?: number | null
  },
): IntegratedDashboardChartData {
  const referenceField = options.referenceField ?? 'cost'
  const principalRowField = referenceRowField[referenceField]
  const orderedSelectedRows = [...selectedRows].sort((left, right) => left.snapshot_date.localeCompare(right.snapshot_date))
  const value = buildPointsForField(orderedSelectedRows, 'total_value')
  const principal = buildPointsForField(orderedSelectedRows, principalRowField)
  const gainLossBand = orderedSelectedRows.flatMap((row) => {
    const rowValue = parseNullableNumber(row.total_value)
    const rowPrincipal = parseNullableNumber(row[principalRowField])
    return rowValue === null || rowPrincipal === null
      ? []
      : [{ time: row.snapshot_date, value: rowValue, principal: rowPrincipal }]
  })
  const dailyProfitChange: Array<ColoredChartPoint | ChartWhitespacePoint> = []
  let previousProfit: number | null = null

  orderedSelectedRows.forEach((row, index) => {
    const currentProfit = parseNullableNumber(row.total_profit_loss)
    const confirmedChange = currentProfit !== null && previousProfit !== null
      ? currentProfit - previousProfit
      : null
    const change = index === orderedSelectedRows.length - 1 && options.liveDailyProfit !== undefined
      ? options.liveDailyProfit
      : confirmedChange
    if (change === null) {
      dailyProfitChange.push({ time: row.snapshot_date })
    } else {
      dailyProfitChange.push({
        time: row.snapshot_date,
        value: change,
        color: change >= 0 ? '#dc2626' : '#2563eb',
      })
    }
    previousProfit = currentProfit
  })

  return {
    value,
    principal,
    dailyProfitChange,
    gainLossBand,
    composition: options.includeComposition ? buildCumulativeComposition(allRows) : [],
  }
}

export function formatDashboardMoney(value: number) {
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(value)
}

export function getDashboardChartLayout() {
  return {
    mainHeight: 320,
    profitHeight: 110,
  }
}

function buildPointsForField(
  rows: DashboardHistoryRow[],
  field: 'total_value' | 'total_invested_principal' | 'total_cost_basis',
): ChartPoint[] {
  return rows.flatMap((row) => {
    const value = parseNullableNumber(row[field])
    return value === null ? [] : [{ time: row.snapshot_date, value }]
  })
}

// 투자원금이 "있는지" — 가장 최근의 non-null 투자원금이 0이 아니면 존재로 본다
// (전량 재투자 시 투자원금이 0이 되어 차트 기준선으로 의미가 없어짐).
export function hasInvestedPrincipal(rows: DashboardHistoryRow[]): boolean {
  const ordered = [...rows].sort((left, right) => left.snapshot_date.localeCompare(right.snapshot_date))
  for (let i = ordered.length - 1; i >= 0; i -= 1) {
    const value = parseNullableNumber(ordered[i].total_invested_principal)
    if (value !== null) return value !== 0
  }
  return false
}

function resolveReferenceDefault(
  referenceDefault: ChartReferenceField | 'auto',
  rows: DashboardHistoryRow[],
): ChartReferenceField {
  if (referenceDefault === 'auto') return hasInvestedPrincipal(rows) ? 'invested' : 'cost'
  return referenceDefault
}

function buildCumulativeComposition(rows: DashboardHistoryRow[]): DashboardBuiltChartSeries[] {
  const individualSeries = buildDashboardChartSeries(
    rows.filter((row) => row.group_kind === 'source' || row.group_kind === 'unclassified'),
    { metric: 'value' },
  )
  const dates = Array.from(new Set(individualSeries.flatMap((series) => series.points.map((point) => point.time)))).sort()
  const cumulativeByDate = new Map(dates.map((snapshotDate) => [snapshotDate, 0]))

  return individualSeries.map((series) => {
    const valueByDate = new Map(series.points.map((point) => [point.time, point.value]))
    return {
      ...series,
      points: dates.map((snapshotDate) => {
        const cumulative = (cumulativeByDate.get(snapshotDate) ?? 0) + (valueByDate.get(snapshotDate) ?? 0)
        cumulativeByDate.set(snapshotDate, cumulative)
        return { time: snapshotDate, value: cumulative }
      }),
    }
  })
}

function parseNullableNumber(value: string | null) {
  if (value === null) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function PortfolioChart(props: Props) {
  if (props.historyRows !== undefined) {
    return (
      <DashboardPortfolioChart
        rows={props.historyRows}
        compositionRows={props.compositionRows}
        includeComposition={props.includeComposition}
        displayCurrency={props.displayCurrency}
        visibleRange={props.visibleRange}
        showGainLossBand={props.showGainLossBand ?? false}
        referenceDefault={props.referenceDefault ?? 'auto'}
      />
    )
  }
  return <LegacyPortfolioChart series={props.series} />
}

function DashboardPortfolioChart({
  rows,
  compositionRows,
  includeComposition,
  displayCurrency,
  visibleRange,
  showGainLossBand,
  referenceDefault,
}: {
  rows: DashboardHistoryRow[]
  compositionRows: DashboardHistoryRow[]
  includeComposition: boolean
  displayCurrency: DisplayCurrency
  visibleRange: ChartVisibleRange
  showGainLossBand: boolean
  referenceDefault: ChartReferenceField | 'auto'
}) {
  const mainContainerRef = useRef<HTMLDivElement>(null)
  const profitContainerRef = useRef<HTMLDivElement>(null)
  const [referenceOverride, setReferenceOverride] = useState<ChartReferenceField | null>(null)
  const referenceField = referenceOverride ?? resolveReferenceDefault(referenceDefault, rows)
  const chartData = useMemo(
    () => buildIntegratedDashboardChartData(compositionRows, rows, { includeComposition, referenceField }),
    [compositionRows, includeComposition, rows, referenceField],
  )
  const hasData = chartData.value.length > 0 || chartData.principal.length > 0

  useEffect(() => {
    if (!mainContainerRef.current || !profitContainerRef.current || !hasData) return
    let cancelled = false
    let mainChart: ReturnType<typeof import('lightweight-charts')['createChart']> | null = null
    let profitChart: ReturnType<typeof import('lightweight-charts')['createChart']> | null = null
    let handleResize: (() => void) | null = null
    let mainVisibleTimeRangeHandler: import('lightweight-charts').TimeRangeChangeEventHandler<import('lightweight-charts').Time> | null = null
    let profitVisibleTimeRangeHandler: import('lightweight-charts').TimeRangeChangeEventHandler<import('lightweight-charts').Time> | null = null

    import('lightweight-charts').then(({ createChart, ColorType, LineStyle }) => {
      if (cancelled || !mainContainerRef.current || !profitContainerRef.current) return
      const layout = getDashboardChartLayout()
      const commonLayout = {
        background: { type: ColorType.Solid, color: 'white' },
        textColor: '#6b7280',
        fontSize: 11,
      }
      const commonGrid = {
        vertLines: { color: '#f3f4f6' },
        horzLines: { color: '#f3f4f6' },
      }
      const applyChartVisibleRange = (chart: ReturnType<typeof createChart>) => {
        if (visibleRange) {
          chart.timeScale().setVisibleRange({
            from: visibleRange.from as import('lightweight-charts').Time,
            to: visibleRange.to as import('lightweight-charts').Time,
          })
        } else {
          chart.timeScale().fitContent()
        }
      }

      mainChart = createChart(mainContainerRef.current, {
        width: mainContainerRef.current.clientWidth,
        height: layout.mainHeight,
        layout: {
          ...commonLayout,
        },
        grid: commonGrid,
        localization: { priceFormatter: formatDashboardMoney },
        leftPriceScale: {
          visible: true,
          borderColor: '#e5e7eb',
          scaleMargins: { top: 0.05, bottom: 0.05 },
        },
        rightPriceScale: { visible: false },
        timeScale: {
          visible: true,
          borderColor: '#e5e7eb',
          fixLeftEdge: true,
          fixRightEdge: false,
          rightOffset: dashboardChartRightPadding,
        },
      })

      profitChart = createChart(profitContainerRef.current, {
        width: profitContainerRef.current.clientWidth,
        height: layout.profitHeight,
        layout: {
          ...commonLayout,
        },
        grid: commonGrid,
        localization: { priceFormatter: formatDashboardMoney },
        leftPriceScale: {
          visible: true,
          borderColor: '#e5e7eb',
          scaleMargins: { top: 0.1, bottom: 0.1 },
        },
        rightPriceScale: { visible: false },
        timeScale: {
          borderColor: '#e5e7eb',
          fixLeftEdge: true,
          fixRightEdge: false,
          rightOffset: dashboardChartRightPadding,
        },
      })

      ;[...chartData.composition].reverse().forEach((item, reverseIndex) => {
        const index = chartData.composition.length - reverseIndex - 1
        const histogram = mainChart!.addHistogramSeries({
          color: dashboardColors[index % dashboardColors.length],
          priceScaleId: 'left',
          priceLineVisible: false,
          lastValueVisible: false,
          priceFormat: dashboardPriceFormat,
        })
        histogram.setData(item.points.map((point) => ({
          time: point.time as import('lightweight-charts').Time,
          value: point.value,
        })))
      })

      const valueSeries = mainChart.addLineSeries({
        color: '#312e81',
        lineWidth: 3,
        lineStyle: LineStyle.Solid,
        priceScaleId: 'left',
        priceLineVisible: false,
        lastValueVisible: true,
        priceFormat: dashboardPriceFormat,
      })
      valueSeries.setData(chartData.value.map(toLightweightPoint))

      const principalSeries = mainChart.addLineSeries({
        color: '#818cf8',
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        priceScaleId: 'left',
        priceLineVisible: false,
        lastValueVisible: false,
        priceFormat: dashboardPriceFormat,
      })
      principalSeries.setData(chartData.principal.map(toLightweightPoint))

      if (showGainLossBand && chartData.gainLossBand.length > 1) {
        const band = new GainLossBandPrimitive(chartData.gainLossBand)
        valueSeries.attachPrimitive(band as unknown as Parameters<typeof valueSeries.attachPrimitive>[0])
      }

      const profitSeries = profitChart.addHistogramSeries({
        priceScaleId: 'left',
        priceLineVisible: false,
        lastValueVisible: false,
        priceFormat: dashboardPriceFormat,
      })
      profitSeries.setData(chartData.dailyProfitChange.map((point) => ({
        time: point.time as import('lightweight-charts').Time,
        ...('value' in point ? { value: point.value, color: point.color } : {}),
      })))

      applyChartVisibleRange(mainChart)
      applyChartVisibleRange(profitChart)
      const ignoredMainTimeRanges = new Set<string>()
      const ignoredProfitTimeRanges = new Set<string>()
      const syncRange = (
        target: ReturnType<typeof import('lightweight-charts')['createChart']>,
        sourceIgnoredRanges: Set<string>,
        targetIgnoredRanges: Set<string>,
        range: import('lightweight-charts').Range<import('lightweight-charts').Time> | null,
      ) => {
        if (!range) return
        const rangeKey = JSON.stringify(range)
        if (sourceIgnoredRanges.delete(rangeKey)) return
        targetIgnoredRanges.add(rangeKey)
        target.timeScale().setVisibleRange(range)
      }
      mainVisibleTimeRangeHandler = (range) => syncRange(
        profitChart!,
        ignoredMainTimeRanges,
        ignoredProfitTimeRanges,
        range,
      )
      profitVisibleTimeRangeHandler = (range) => syncRange(
        mainChart!,
        ignoredProfitTimeRanges,
        ignoredMainTimeRanges,
        range,
      )
      mainChart.timeScale().subscribeVisibleTimeRangeChange(mainVisibleTimeRangeHandler)
      profitChart.timeScale().subscribeVisibleTimeRangeChange(profitVisibleTimeRangeHandler)

      handleResize = () => {
        if (mainContainerRef.current && mainChart) {
          mainChart.applyOptions({ width: mainContainerRef.current.clientWidth })
          applyChartVisibleRange(mainChart)
        }
        if (profitContainerRef.current && profitChart) {
          profitChart.applyOptions({ width: profitContainerRef.current.clientWidth })
          applyChartVisibleRange(profitChart)
        }
      }
      window.addEventListener('resize', handleResize)
    })

    return () => {
      cancelled = true
      if (handleResize) window.removeEventListener('resize', handleResize)
      if (mainChart && mainVisibleTimeRangeHandler) {
        mainChart.timeScale().unsubscribeVisibleTimeRangeChange(mainVisibleTimeRangeHandler)
      }
      if (profitChart && profitVisibleTimeRangeHandler) {
        profitChart.timeScale().unsubscribeVisibleTimeRangeChange(profitVisibleTimeRangeHandler)
      }
      mainChart?.remove()
      profitChart?.remove()
    }
  }, [chartData, hasData, visibleRange, showGainLossBand])

  if (!hasData) {
    return <div className="flex h-60 items-center justify-center text-sm text-gray-400">차트 데이터가 없습니다.</div>
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-500">
        <strong className="text-gray-600">{displayCurrency}</strong>
        <Legend color="#312e81" label="평가금액" />
        <ReferenceFieldToggle value={referenceField} onChange={setReferenceOverride} />
        {chartData.composition.map((series, index) => (
          <HistogramLegend
            key={series.id}
            color={dashboardColors[index % dashboardColors.length]}
            label={series.name}
          />
        ))}
      </div>
      <div className="text-xs font-medium text-gray-500">평가금액 · 그룹 구성</div>
      <div ref={mainContainerRef} className="w-full" />
      <div className="mt-2 border-t border-gray-100 pt-2 text-xs font-medium text-gray-500">일별손익</div>
      <div ref={profitContainerRef} className="w-full" />
    </div>
  )
}

const dashboardPriceFormat = {
  type: 'custom' as const,
  minMove: 1,
  formatter: formatDashboardMoney,
}

function toLightweightPoint(point: ChartPoint) {
  return {
    time: point.time as import('lightweight-charts').Time,
    value: point.value,
  }
}

// Faintly shade the gap between the 평가금액 and 잔여원금 lines: red where the
// portfolio is in profit, blue where it is at a loss — the way most brokerage
// apps visualise unrealised P&L. lightweight-charts has no native "fill between
// two moving lines" series, so we draw it as a series primitive that, on every
// redraw, projects both lines to pixels and fills the polygon (splitting any
// segment where the lines cross so each side gets its own colour).
const gainBandColor = 'rgba(220, 38, 38, 0.14)'
const lossBandColor = 'rgba(37, 99, 235, 0.14)'

type BandRenderScope = {
  context: CanvasRenderingContext2D
  horizontalPixelRatio: number
  verticalPixelRatio: number
}
type BandRenderTarget = { useBitmapCoordinateSpace: (callback: (scope: BandRenderScope) => void) => void }
type BandCoordSeries = { priceToCoordinate: (price: number) => number | null }
type BandCoordChart = { timeScale: () => { timeToCoordinate: (time: unknown) => number | null } }

class GainLossBandPrimitive {
  private _chart: BandCoordChart | null = null
  private _series: BandCoordSeries | null = null
  private readonly _data: GainLossBandPoint[]
  private readonly _paneViews: GainLossBandPaneView[]

  constructor(data: GainLossBandPoint[]) {
    this._data = data
    this._paneViews = [new GainLossBandPaneView(this)]
  }

  attached(param: { chart: BandCoordChart; series: BandCoordSeries }) {
    this._chart = param.chart
    this._series = param.series
  }

  detached() {
    this._chart = null
    this._series = null
  }

  updateAllViews() {}

  paneViews() {
    return this._paneViews
  }

  get chart() {
    return this._chart
  }

  get series() {
    return this._series
  }

  get data() {
    return this._data
  }
}

class GainLossBandPaneView {
  private readonly _renderer: GainLossBandRenderer

  constructor(source: GainLossBandPrimitive) {
    this._renderer = new GainLossBandRenderer(source)
  }

  zOrder() {
    return 'top' as const
  }

  renderer() {
    return this._renderer
  }
}

type ProjectedBandPoint = { x: number; valueY: number; principalY: number; gain: boolean }

class GainLossBandRenderer {
  constructor(private readonly _source: GainLossBandPrimitive) {}

  draw(target: BandRenderTarget) {
    const chart = this._source.chart
    const series = this._source.series
    if (!chart || !series) return
    const timeScale = chart.timeScale()
    const points = this._source.data
      .map((point): ProjectedBandPoint | null => {
        const x = timeScale.timeToCoordinate(point.time as unknown)
        const valueY = series.priceToCoordinate(point.value)
        const principalY = series.priceToCoordinate(point.principal)
        return x === null || valueY === null || principalY === null
          ? null
          : { x, valueY, principalY, gain: point.value >= point.principal }
      })
      .filter((point): point is ProjectedBandPoint => point !== null)
    if (points.length < 2) return

    target.useBitmapCoordinateSpace(({ context: ctx, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
      const fill = (color: string, corners: Array<[number, number]>) => {
        ctx.beginPath()
        corners.forEach(([x, y], index) => {
          const px = x * hr
          const py = y * vr
          if (index === 0) ctx.moveTo(px, py)
          else ctx.lineTo(px, py)
        })
        ctx.closePath()
        ctx.fillStyle = color
        ctx.fill()
      }

      for (let i = 0; i < points.length - 1; i += 1) {
        const a = points[i]
        const b = points[i + 1]
        const gapA = a.valueY - a.principalY
        const gapB = b.valueY - b.principalY
        const crosses = gapA !== 0 && gapB !== 0 && gapA < 0 !== gapB < 0
        if (!crosses) {
          fill(a.gain ? gainBandColor : lossBandColor, [
            [a.x, a.valueY],
            [b.x, b.valueY],
            [b.x, b.principalY],
            [a.x, a.principalY],
          ])
          continue
        }
        const t = gapA / (gapA - gapB)
        const xCross = a.x + t * (b.x - a.x)
        const yCross = a.valueY + t * (b.valueY - a.valueY)
        fill(a.gain ? gainBandColor : lossBandColor, [
          [a.x, a.valueY],
          [xCross, yCross],
          [a.x, a.principalY],
        ])
        fill(b.gain ? gainBandColor : lossBandColor, [
          [xCross, yCross],
          [b.x, b.valueY],
          [b.x, b.principalY],
        ])
      }
    })
  }
}

const dashboardKindOrder: Record<DashboardHistoryGroupKind, number> = {
  total: 0,
  source: 1,
  combined: 2,
  unclassified: 3,
}

function compareDashboardSeries(left: DashboardBuiltChartSeries, right: DashboardBuiltChartSeries) {
  const kindDiff = dashboardKindOrder[left.kind] - dashboardKindOrder[right.kind]
  if (kindDiff !== 0) return kindDiff
  const nameDiff = left.name.localeCompare(right.name, 'ko')
  if (nameDiff !== 0) return nameDiff
  return left.id.localeCompare(right.id)
}

function LegacyPortfolioChart({ series }: { series: ScopedPortfolioHistory['series'] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartSeries = useMemo(() => buildChartSeries(series), [series])
  const hasData = currencies.some((currency) => legacyMeasures.some((measure) => chartSeries[currency][measure].length > 0))

  useEffect(() => {
    if (!containerRef.current || !hasData) return
    let cancelled = false
    let chart: ReturnType<typeof import('lightweight-charts')['createChart']> | null = null
    let handleResize: (() => void) | null = null

    import('lightweight-charts').then(({ createChart, ColorType, LineStyle }) => {
      if (cancelled || !containerRef.current) return
      chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 280,
        layout: {
          background: { type: ColorType.Solid, color: 'white' },
          textColor: '#6b7280',
          fontSize: 11,
        },
        grid: {
          vertLines: { color: '#f3f4f6' },
          horzLines: { color: '#f3f4f6' },
        },
        leftPriceScale: { visible: true, borderColor: '#e5e7eb' },
        rightPriceScale: { visible: true, borderColor: '#e5e7eb' },
        timeScale: { borderColor: '#e5e7eb', fixLeftEdge: true, fixRightEdge: true },
      })

      for (const currency of currencies) {
        for (const measure of legacyMeasures) {
          const lineSeries = chart.addLineSeries({
            color: legacyColors[currency][measure],
            lineWidth: measure === 'value' ? 2 : 1,
            lineStyle: measure === 'value' ? LineStyle.Solid : measure === 'cost' ? LineStyle.Dashed : LineStyle.Dotted,
            priceScaleId: currency === 'KRW' ? 'left' : 'right',
            priceLineVisible: false,
            lastValueVisible: measure === 'value',
          })
          lineSeries.setData(chartSeries[currency][measure].map((point) => ({
            time: point.time as import('lightweight-charts').Time,
            value: point.value,
          })))
        }
      }

      chart.timeScale().fitContent()
      handleResize = () => {
        if (containerRef.current && chart) chart.applyOptions({ width: containerRef.current.clientWidth })
      }
      window.addEventListener('resize', handleResize)
    })

    return () => {
      cancelled = true
      if (handleResize) window.removeEventListener('resize', handleResize)
      chart?.remove()
    }
  }, [chartSeries, hasData])

  if (!hasData) {
    return <div className="flex h-60 items-center justify-center text-sm text-gray-400">차트 데이터가 없습니다.</div>
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-gray-500">
        {currencies.map((currency) => (
          <div key={currency} className="flex items-center gap-3">
            <strong className="text-gray-600">{currency}</strong>
            <Legend color={legacyColors[currency].value} label="평가금액" />
            <Legend color={legacyColors[currency].cost} label="투자원금" dashed />
            <Legend color={legacyColors[currency].profit} label="평가손익" dotted />
          </div>
        ))}
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  )
}

function Legend({ color, label, dashed, dotted }: { color: string; label: string; dashed?: boolean; dotted?: boolean }) {
  return (
    <span className="flex items-center gap-1">
      <span
        className={`inline-block w-4 border-t-2 ${dashed ? 'border-dashed' : dotted ? 'border-dotted' : ''}`}
        style={{ borderColor: color }}
      />
      {label}
    </span>
  )
}

function HistogramLegend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="inline-block h-2.5 w-3 rounded-sm" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}

const referenceToggleOptions: ChartReferenceField[] = ['invested', 'cost']

function ReferenceFieldToggle({
  value,
  onChange,
}: {
  value: ChartReferenceField
  onChange: (value: ChartReferenceField) => void
}) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block w-4 border-t-2 border-dashed" style={{ borderColor: '#818cf8' }} />
      <span className="inline-flex rounded-md border border-gray-200 bg-white p-0.5" role="group" aria-label="원금 기준">
        {referenceToggleOptions.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={value === option}
            className={[
              'rounded px-1.5 py-0.5 text-xs font-medium transition-colors',
              value === option ? 'bg-indigo-50 text-indigo-700' : 'text-gray-400 hover:text-gray-600',
            ].join(' ')}
            onClick={() => onChange(option)}
          >
            {referenceFieldLabel[option]}
          </button>
        ))}
      </span>
    </span>
  )
}
