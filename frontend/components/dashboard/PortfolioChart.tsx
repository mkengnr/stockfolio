'use client'

import { useEffect, useRef } from 'react'
import type { Snapshot } from '@/lib/types'

interface DayPoint {
  date: string        // YYYY-MM-DD
  totalValue: number
  totalCost: number
}

interface Props {
  /** Pre-aggregated day points from all holdings */
  data: DayPoint[]
}

export function PortfolioChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return

    let chart: ReturnType<typeof import('lightweight-charts')['createChart']> | null = null

    import('lightweight-charts').then(({ createChart, ColorType, LineStyle }) => {
      if (!containerRef.current) return
      chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 240,
        layout: {
          background: { type: ColorType.Solid, color: 'white' },
          textColor: '#6b7280',
          fontSize: 11,
        },
        grid: {
          vertLines: { color: '#f3f4f6' },
          horzLines: { color: '#f3f4f6' },
        },
        rightPriceScale: { borderColor: '#e5e7eb' },
        timeScale: { borderColor: '#e5e7eb', fixLeftEdge: true, fixRightEdge: true },
      })

      const valueSeries = chart.addLineSeries({
        color: '#6366f1',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      })
      const costSeries = chart.addLineSeries({
        color: '#d1d5db',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
      })

      valueSeries.setData(data.map((d) => ({ time: d.date as import('lightweight-charts').Time, value: d.totalValue })))
      costSeries.setData(data.map((d) => ({ time: d.date as import('lightweight-charts').Time, value: d.totalCost })))

      chart.timeScale().fitContent()

      const handleResize = () => {
        if (containerRef.current && chart) {
          chart.applyOptions({ width: containerRef.current.clientWidth })
        }
      }
      window.addEventListener('resize', handleResize)

      return () => window.removeEventListener('resize', handleResize)
    })

    return () => {
      chart?.remove()
    }
  }, [data])

  if (data.length === 0) {
    return (
      <div className="flex h-60 items-center justify-center text-sm text-gray-400">
        차트 데이터를 불러오는 중...
      </div>
    )
  }

  return (
    <div>
      <div className="mb-2 flex items-center gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-4 rounded bg-brand-500" /> 평가금액
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-px w-4 border-t-2 border-dashed border-gray-300" /> 투자원금
        </span>
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  )
}

/** Aggregate per-holding snapshots into daily portfolio totals */
export function buildChartData(
  holdings: Array<{ cost_basis: string | null; quantity: string; snapshots: Snapshot[] }>,
): DayPoint[] {
  const byDate = new Map<string, { value: number; cost: number }>()

  for (const h of holdings) {
    const cost = parseFloat(h.cost_basis ?? '0')
    for (const s of h.snapshots) {
      const existing = byDate.get(s.snapshot_date) ?? { value: 0, cost: 0 }
      byDate.set(s.snapshot_date, {
        value: existing.value + parseFloat(s.total_value),
        cost: existing.cost + cost,
      })
    }
  }

  return Array.from(byDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, { value, cost }]) => ({ date, totalValue: value, totalCost: cost }))
}
