'use client'

import { useEffect, useMemo, useRef } from 'react'
import type { Currency, DashboardHistoryGroupKind, DashboardHistoryRow, DisplayCurrency, ScopedPortfolioHistory } from '@/lib/types'
import type { DashboardChartMetric, DashboardChartView } from './DashboardChartControls'

type LegacyMeasure = 'value' | 'cost' | 'profit'
type ChartPoint = { time: string; value: number }
type CurrencyChartSeries = Record<LegacyMeasure, ChartPoint[]>

export interface DashboardBuiltChartSeries {
  id: string
  name: string
  kind: DashboardHistoryGroupKind
  points: ChartPoint[]
}

type LegacyProps = {
  series: ScopedPortfolioHistory['series']
  historyRows?: never
  displayCurrency?: never
  metric?: never
  includeGroups?: never
}

type DashboardProps = {
  historyRows: DashboardHistoryRow[]
  displayCurrency: DisplayCurrency
  metric: DashboardChartMetric
  view: DashboardChartView
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

export function PortfolioChart(props: Props) {
  if (props.historyRows !== undefined) {
    return (
      <DashboardPortfolioChart
        rows={props.historyRows}
        displayCurrency={props.displayCurrency}
        metric={props.metric}
        view={props.view}
      />
    )
  }
  return <LegacyPortfolioChart series={props.series} />
}

function DashboardPortfolioChart({
  rows,
  displayCurrency,
  metric,
  view,
}: {
  rows: DashboardHistoryRow[]
  displayCurrency: DisplayCurrency
  metric: DashboardChartMetric
  view: DashboardChartView
}) {
  const chartSeries = useMemo(() => buildDashboardChartSeries(rows, { metric }), [rows, metric])
  const hasData = chartSeries.some((series) => series.points.length > 0)

  if (!hasData) {
    return <div className="flex h-60 items-center justify-center text-sm text-gray-400">차트 데이터가 없습니다.</div>
  }

  if (view === 'separate') {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        {chartSeries.map((series, index) => (
          <div key={series.id} className="rounded-xl border border-gray-100 p-3">
            <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
              <Legend color={dashboardColors[index % dashboardColors.length]} label={series.name} dashed={series.kind !== 'total'} />
              <span>{displayCurrency}</span>
            </div>
            <DashboardSingleChart
              series={[series]}
              height={220}
              colorOffset={index}
              showLegend={false}
            />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-500">
        <strong className="text-gray-600">{displayCurrency}</strong>
        {chartSeries.map((series, index) => (
          <Legend
            key={series.id}
            color={dashboardColors[index % dashboardColors.length]}
            label={series.name}
            dashed={series.kind !== 'total'}
          />
        ))}
      </div>
      <DashboardSingleChart series={chartSeries} />
    </div>
  )
}

function DashboardSingleChart({
  series,
  height = 280,
  colorOffset = 0,
}: {
  series: DashboardBuiltChartSeries[]
  height?: number
  colorOffset?: number
  showLegend?: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const hasData = series.some((item) => item.points.length > 0)

  useEffect(() => {
    if (!containerRef.current || !hasData) return
    let cancelled = false
    let chart: ReturnType<typeof import('lightweight-charts')['createChart']> | null = null
    let handleResize: (() => void) | null = null

    import('lightweight-charts').then(({ createChart, ColorType, LineStyle }) => {
      if (cancelled || !containerRef.current) return
      chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height,
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
        rightPriceScale: { visible: false },
        timeScale: { borderColor: '#e5e7eb', fixLeftEdge: true, fixRightEdge: true },
      })

      series.forEach((item, index) => {
        const lineSeries = chart!.addLineSeries({
          color: dashboardColors[(index + colorOffset) % dashboardColors.length],
          lineWidth: item.kind === 'total' ? 2 : 1,
          lineStyle: item.kind === 'total' ? LineStyle.Solid : LineStyle.Dashed,
          priceScaleId: 'left',
          priceLineVisible: false,
          lastValueVisible: item.kind === 'total',
        })
        lineSeries.setData(item.points.map((point) => ({
          time: point.time as import('lightweight-charts').Time,
          value: point.value,
        })))
      })

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
  }, [series, hasData, height, colorOffset])

  if (!hasData) {
    return <div className="flex h-60 items-center justify-center text-sm text-gray-400">차트 데이터가 없습니다.</div>
  }

  return <div ref={containerRef} className="w-full" />
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
