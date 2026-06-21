'use client'

import { useEffect, useState } from 'react'
import useSWR from 'swr'
import { DashboardOverview } from '@/components/dashboard/DashboardOverview'
import { DashboardLoadError } from '@/components/dashboard/DashboardLoadError'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { fetcher, portfolioApi } from '@/lib/api'
import type { DashboardResponse, DisplayCurrency, Label } from '@/lib/types'

function DashboardContent() {
  const [displayCurrency, setDisplayCurrency] = useState<DisplayCurrency>('KRW')
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const { data: dashboard, error, isLoading, isValidating, mutate } = useSWR<DashboardResponse>(portfolioApi.dashboardPath(displayCurrency), fetcher, {
    refreshInterval: 30_000,
  })
  const { data: labels } = useSWR<Label[]>('/api/groups/labels', fetcher)

  useEffect(() => {
    if (dashboard) setLastUpdated(new Date())
  }, [dashboard])

  if (error) return <DashboardLoadError onRetry={() => void mutate()} />
  if (isLoading || !dashboard) return <PageLoader />

  return (
    <DashboardOverview
      dashboard={dashboard}
      displayCurrency={displayCurrency}
      onDisplayCurrencyChange={setDisplayCurrency}
      onRefresh={() => void mutate()}
      isRefreshing={isValidating}
      lastUpdated={lastUpdated}
      labels={labels ?? []}
    />
  )
}

export default function DashboardPage() {
  return <AuthGuard><DashboardContent /></AuthGuard>
}
