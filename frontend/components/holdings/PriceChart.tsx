'use client'

import { useEffect, useRef } from 'react'
import type { Snapshot, Transaction } from '@/lib/types'
import { toIsoDateKey } from '@/lib/chartTime'

interface Props {
  snapshots: Snapshot[]
  currency: 'KRW' | 'USD'
  currentPrice: string | null
  transactions: Transaction[]
}

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

function toLocalDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function PriceChart({ snapshots, currency }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || snapshots.length === 0) return

    let cancelled = false
    let chart: ReturnType<typeof import('lightweight-charts')['createChart']> | null = null
    let handleResize: (() => void) | null = null

    import('lightweight-charts').then(({ createChart, ColorType }) => {
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
          vertLines: { color: '#f9fafb' },
          horzLines: { color: '#f3f4f6' },
        },
        rightPriceScale: {
          borderColor: '#e5e7eb',
          scaleMargins: { top: 0.1, bottom: 0.1 },
        },
        timeScale: { borderColor: '#e5e7eb', fixLeftEdge: true, fixRightEdge: true },
        localization: {
          priceFormatter: (price: number) => {
            if (currency === 'KRW') return `₩${Math.round(price).toLocaleString('ko-KR')}`
            return `$${price.toFixed(2)}`
          },
        },
      })

      const areaSeries = chart.addAreaSeries({
        lineColor: '#6366f1',
        topColor: '#6366f120',
        bottomColor: '#6366f100',
        lineWidth: 2,
        priceLineVisible: true,
        priceLineColor: '#6366f180',
      })

      areaSeries.setData(
        snapshots.map((s) => ({
          time: s.snapshot_date as import('lightweight-charts').Time,
          value: parseFloat(s.close_price),
        })),
      )

      chart.timeScale().fitContent()

      handleResize = () => {
        if (containerRef.current && chart) {
          chart.applyOptions({ width: containerRef.current.clientWidth })
        }
      }
      window.addEventListener('resize', handleResize)
    })

    return () => {
      cancelled = true
      if (handleResize) window.removeEventListener('resize', handleResize)
      chart?.remove()
    }
  }, [snapshots, currency])

  if (snapshots.length === 0) {
    return (
      <div className="flex h-[280px] items-center justify-center text-sm text-gray-400">
        스냅샷 데이터가 없습니다. 첫 장 마감 후 차트가 표시됩니다.
      </div>
    )
  }

  return <div ref={containerRef} className="w-full" />
}
