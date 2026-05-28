'use client'

import useSWR from 'swr'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { PortfolioSummary } from '@/components/dashboard/PortfolioSummary'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import { PortfolioChart, buildChartData } from '@/components/dashboard/PortfolioChart'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { fetcher } from '@/lib/api'
import type { Holding, HoldingDetail } from '@/lib/types'
import Link from 'next/link'
import useSWRImmutable from 'swr/immutable'

function DashboardContent() {
  const { data: holdings, isLoading } = useSWR<Holding[]>('/api/holdings', fetcher, {
    refreshInterval: 30_000,
  })

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
