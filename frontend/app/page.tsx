'use client'

import { useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import { PortfolioChart } from '@/components/dashboard/PortfolioChart'
import { PortfolioSummary } from '@/components/dashboard/PortfolioSummary'
import { ScopeFilter } from '@/components/dashboard/ScopeFilter'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { fetcher, portfolioApi } from '@/lib/api'
import type {
  Label, PortfolioScope, PortfolioSummary as SummaryPayload, RollupGroup,
  ScopedPortfolioHistory, ScopedPortfolioHoldings, SourceGroup,
} from '@/lib/types'

function DashboardContent() {
  const [scope, setScope] = useState<PortfolioScope>({ kind: 'all' })
  const { data: sources = [] } = useSWR<SourceGroup[]>('/api/groups/sources', fetcher)
  const { data: rollups = [] } = useSWR<RollupGroup[]>('/api/groups/rollups', fetcher)
  const { data: labels = [] } = useSWR<Label[]>('/api/groups/labels', fetcher)
  const { data: summary, isLoading: summaryLoading } = useSWR<SummaryPayload>(portfolioApi.summaryPath(scope), fetcher, {
    refreshInterval: 30_000,
  })
  const { data: holdings, isLoading: holdingsLoading } = useSWR<ScopedPortfolioHoldings>(portfolioApi.holdingsPath(scope), fetcher, {
    refreshInterval: 30_000,
  })
  const { data: history } = useSWR<ScopedPortfolioHistory>(portfolioApi.historyPath(scope), fetcher)

  if (summaryLoading || holdingsLoading || !summary || !holdings) return <PageLoader />

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-gray-900">대시보드</h1>
        <div className="flex flex-wrap items-center gap-3">
          <ScopeFilter value={scope} sources={sources} rollups={rollups} labels={labels} onChange={setScope} />
          <Link href="/holdings/new" className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-600">
            + 종목 등록
          </Link>
        </div>
      </div>

      <PortfolioSummary summary={summary} />

      <Card>
        <h2 className="font-semibold text-gray-900">포트폴리오 변화</h2>
        <p className="mb-4 mt-1 text-sm text-gray-500">
          KRW는 왼쪽 축, USD는 오른쪽 축에 표시합니다. 서로 다른 통화는 합산하지 않습니다.
        </p>
        <PortfolioChart series={history?.series ?? { KRW: [], USD: [] }} />
      </Card>

      <Card noPad>
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-semibold text-gray-900">보유 종목</h2>
        </div>
        <HoldingsTable holdings={holdings.holdings} />
      </Card>
    </div>
  )
}

export default function DashboardPage() {
  return <AuthGuard><DashboardContent /></AuthGuard>
}
