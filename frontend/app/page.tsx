'use client'

import useSWR from 'swr'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { PortfolioSummary } from '@/components/dashboard/PortfolioSummary'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import { PortfolioChart, buildChartData } from '@/components/dashboard/PortfolioChart'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { fetcher } from '@/lib/api'
import type { Holding, PortfolioHistory } from '@/lib/types'
import Link from 'next/link'

const currencyLabels = {
  KRW: '원화 자산 (KRW)',
  USD: '달러 자산 (USD)',
}

function DashboardContent() {
  const { data: holdings, isLoading } = useSWR<Holding[]>('/api/holdings', fetcher, {
    refreshInterval: 30_000,
  })
  const { data: history } = useSWR<PortfolioHistory>('/api/portfolio/history', fetcher)

  if (isLoading || !holdings) return <PageLoader />

  const activeHoldings = holdings.filter((h) => h.is_active)

  return (
    <div className="flex flex-col gap-6">
      {/* Top bar */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">대시보드</h1>
        <Link
          href="/holdings/new"
          className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
        >
          + 종목 등록
        </Link>
      </div>

      {/* Summary cards */}
      <PortfolioSummary holdings={activeHoldings} />

      {/* Portfolio chart */}
      <Card>
        <h2 className="font-semibold text-gray-900">포트폴리오 변화</h2>
        <p className="mb-4 mt-1 text-sm text-gray-500">
          통화가 다른 자산은 합산하지 않고 원화와 달러로 나누어 표시합니다.
        </p>
        <div className="flex flex-col gap-6">
          {(Object.entries(history?.series ?? {}) as Array<['KRW' | 'USD', PortfolioHistory['series']['KRW']]>)
            .filter(([, points]) => points.length > 0)
            .map(([currency, points]) => (
              <div key={currency}>
                <p className="mb-2 text-xs font-semibold text-gray-500">{currencyLabels[currency]}</p>
                <PortfolioChart
                  data={points.map((point) => ({
                    date: point.snapshot_date,
                    totalValue: parseFloat(point.total_value),
                    totalCost: parseFloat(point.total_cost_basis),
                  }))}
                />
              </div>
            ))}
          {!Object.values(history?.series ?? {}).some((points) => points.length > 0) && (
            <PortfolioChart data={[]} />
          )}
        </div>
      </Card>

      {/* Holdings table */}
      <Card noPad>
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-semibold text-gray-900">보유 종목</h2>
        </div>
        <HoldingsTable holdings={activeHoldings} />
      </Card>
    </div>
  )
}

export default function DashboardPage() {
  return (
    <AuthGuard>
      <DashboardContent />
    </AuthGuard>
  )
}
