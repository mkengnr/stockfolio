'use client'

import { useEffect, useMemo, useRef } from 'react'
import type { Currency, ScopedPortfolioHistory } from '@/lib/types'

type Measure = 'value' | 'cost' | 'profit'
type ChartPoint = { time: string; value: number }
type CurrencyChartSeries = Record<Measure, ChartPoint[]>

const currencies: Currency[] = ['KRW', 'USD']
const measures: Measure[] = ['value', 'cost', 'profit']

const colors: Record<Currency, Record<Measure, string>> = {
  KRW: { value: '#4f46e5', cost: '#a5b4fc', profit: '#818cf8' },
  USD: { value: '#059669', cost: '#a7f3d0', profit: '#34d399' },
}

const fieldByMeasure = {
  value: 'total_value',
  cost: 'total_invested_principal',
  profit: 'total_profit_loss',
} as const

interface Props {
  series: ScopedPortfolioHistory['series']
}

export function buildChartSeries(series: ScopedPortfolioHistory['series']): Record<Currency, CurrencyChartSeries> {
  return Object.fromEntries(currencies.map((currency) => [
    currency,
    Object.fromEntries(measures.map((measure) => [
      measure,
      (series[currency] ?? [])
        .filter((point) => point[fieldByMeasure[measure]] !== null)
        .map((point) => ({
          time: point.snapshot_date,
          value: parseFloat(point[fieldByMeasure[measure]]!),
        })),
    ])),
  ])) as Record<Currency, CurrencyChartSeries>
}

export function PortfolioChart({ series }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartSeries = useMemo(() => buildChartSeries(series), [series])
  const hasData = currencies.some((currency) => measures.some((measure) => chartSeries[currency][measure].length > 0))

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
        for (const measure of measures) {
          const lineSeries = chart.addLineSeries({
            color: colors[currency][measure],
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
            <Legend color={colors[currency].value} label="평가금액" />
            <Legend color={colors[currency].cost} label="투자원금" dashed />
            <Legend color={colors[currency].profit} label="평가손익" dotted />
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
