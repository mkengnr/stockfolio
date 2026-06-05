'use client'

import { useEffect, useRef } from 'react'
import type { Snapshot } from '@/lib/types'

interface Props {
  snapshots: Snapshot[]
  currency: 'KRW' | 'USD'
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
