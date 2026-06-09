'use client'

import { useEffect, useMemo, useRef } from 'react'
import type { Currency, DashboardHistoryGroupKind, DashboardHistoryRow, DisplayCurrency, ScopedPortfolioHistory } from '@/lib/types'

type LegacyMeasure = 'value' | 'cost' | 'profit'
type DashboardChartMetric = 'value' | 'principal' | 'profit'
type ChartPoint = { time: string; value: number }
type ColoredChartPoint = ChartPoint & { color: string }
type CurrencyChartSeries = Record<LegacyMeasure, ChartPoint[]>

export interface DashboardBuiltChartSeries {
  id: string
  name: string
  kind: DashboardHistoryGroupKind
  points: ChartPoint[]
}

export interface IntegratedDashboardChartData {
  value: ChartPoint[]
  principal: ChartPoint[]
  dailyProfitChange: ColoredChartPoint[]
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

const legacyFieldByMeasure = {
  value: 'total_value',
  cost: 'total_invested_principal',
  profit: 'total_profit_loss',
} as const

const dashboardFieldByMetric = {
  value: 'total_value',
  principal: 'total_invested_principal',
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

export function buildIntegratedDashboardChartData(
  allRows: DashboardHistoryRow[],
  selectedRows: DashboardHistoryRow[],
  options: { includeComposition: boolean },
): IntegratedDashboardChartData {
  const orderedSelectedRows = [...selectedRows].sort((left, right) => left.snapshot_date.localeCompare(right.snapshot_date))
  const value = buildPointsForField(orderedSelectedRows, 'total_value')
  const principal = buildPointsForField(orderedSelectedRows, 'total_invested_principal')
  const dailyProfitChange: ColoredChartPoint[] = []
  let previousProfit: number | null = null

  for (const row of orderedSelectedRows) {
    const currentProfit = parseNullableNumber(row.total_profit_loss)
    if (currentProfit !== null && previousProfit !== null) {
      const change = currentProfit - previousProfit
      dailyProfitChange.push({
        time: row.snapshot_date,
        value: change,
        color: change >= 0 ? '#16a34a' : '#dc2626',
      })
    }
    if (currentProfit !== null) previousProfit = currentProfit
  }

  return {
    value,
    principal,
    dailyProfitChange,
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
  field: 'total_value' | 'total_invested_principal',
): ChartPoint[] {
  return rows.flatMap((row) => {
    const value = parseNullableNumber(row[field])
    return value === null ? [] : [{ time: row.snapshot_date, value }]
  })
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
}: {
  rows: DashboardHistoryRow[]
  compositionRows: DashboardHistoryRow[]
  includeComposition: boolean
  displayCurrency: DisplayCurrency
}) {
  const mainContainerRef = useRef<HTMLDivElement>(null)
  const profitContainerRef = useRef<HTMLDivElement>(null)
  const chartData = useMemo(
    () => buildIntegratedDashboardChartData(compositionRows, rows, { includeComposition }),
    [compositionRows, includeComposition, rows],
  )
  const hasData = chartData.value.length > 0 || chartData.principal.length > 0

  useEffect(() => {
    if (!mainContainerRef.current || !profitContainerRef.current || !hasData) return
    let cancelled = false
    let mainChart: ReturnType<typeof import('lightweight-charts')['createChart']> | null = null
    let profitChart: ReturnType<typeof import('lightweight-charts')['createChart']> | null = null
    let handleResize: (() => void) | null = null

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
          visible: false,
          borderColor: '#e5e7eb',
          fixLeftEdge: true,
          fixRightEdge: true,
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
        timeScale: { borderColor: '#e5e7eb', fixLeftEdge: true, fixRightEdge: true },
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

      const profitSeries = profitChart.addHistogramSeries({
        priceScaleId: 'left',
        priceLineVisible: false,
        lastValueVisible: false,
        priceFormat: dashboardPriceFormat,
      })
      profitSeries.setData(chartData.dailyProfitChange.map((point) => ({
        time: point.time as import('lightweight-charts').Time,
        value: point.value,
        color: point.color,
      })))

      mainChart.timeScale().fitContent()
      profitChart.timeScale().fitContent()
      let syncingTimeScale = false
      const syncRange = (
        target: ReturnType<typeof import('lightweight-charts')['createChart']>,
        range: import('lightweight-charts').LogicalRange | null,
      ) => {
        if (!range || syncingTimeScale) return
        syncingTimeScale = true
        target.timeScale().setVisibleLogicalRange(range)
        syncingTimeScale = false
      }
      mainChart.timeScale().subscribeVisibleLogicalRangeChange((range) => syncRange(profitChart!, range))
      profitChart.timeScale().subscribeVisibleLogicalRangeChange((range) => syncRange(mainChart!, range))

      handleResize = () => {
        if (mainContainerRef.current && mainChart) {
          mainChart.applyOptions({ width: mainContainerRef.current.clientWidth })
        }
        if (profitContainerRef.current && profitChart) {
          profitChart.applyOptions({ width: profitContainerRef.current.clientWidth })
        }
      }
      window.addEventListener('resize', handleResize)
    })

    return () => {
      cancelled = true
      if (handleResize) window.removeEventListener('resize', handleResize)
      mainChart?.remove()
      profitChart?.remove()
    }
  }, [chartData, hasData])

  if (!hasData) {
    return <div className="flex h-60 items-center justify-center text-sm text-gray-400">차트 데이터가 없습니다.</div>
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-500">
        <strong className="text-gray-600">{displayCurrency}</strong>
        <Legend color="#312e81" label="평가금액" />
        <Legend color="#818cf8" label="투자원금" dashed />
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
