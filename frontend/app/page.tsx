'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { DashboardOverview } from '@/components/dashboard/DashboardOverview'
import { DashboardLoadError } from '@/components/dashboard/DashboardLoadError'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { fetcher, portfolioApi } from '@/lib/api'
import type { DashboardResponse, DisplayCurrency } from '@/lib/types'

function DashboardContent() {
  const [displayCurrency, setDisplayCurrency] = useState<DisplayCurrency>('KRW')
  const { data: dashboard, error, isLoading, mutate } = useSWR<DashboardResponse>(portfolioApi.dashboardPath(displayCurrency), fetcher, {
    refreshInterval: 30_000,
  })

  if (error) return <DashboardLoadError onRetry={() => void mutate()} />
  if (isLoading || !dashboard) return <PageLoader />

  return (
    <DashboardOverview
      dashboard={dashboard}
      displayCurrency={displayCurrency}
      onDisplayCurrencyChange={setDisplayCurrency}
    />
  )
}

export default function DashboardPage() {
  return <AuthGuard><DashboardContent /></AuthGuard>
}
