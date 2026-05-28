'use client'

import { use } from 'react'
import useSWR from 'swr'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { TagDetailView } from '@/components/tags/TagDetail'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { fetcher } from '@/lib/api'
import type { Holding } from '@/lib/types'

function TagPageContent({ id }: { id: string }) {
  const { data: holdings, isLoading } = useSWR<Holding[]>('/api/holdings', fetcher, {
    refreshInterval: 30_000,
  })

  if (isLoading || !holdings) return <PageLoader />

  return <TagDetailView tagId={id} allHoldings={holdings} />
}

export default function TagPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <AuthGuard>
      <TagPageContent id={id} />
    </AuthGuard>
  )
}
