'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { PriceChart } from '@/components/holdings/PriceChart'
import { HoldingPerformanceSummary } from '@/components/holdings/HoldingPerformanceSummary'
import { HoldingGroupBreakdownTable } from '@/components/holdings/HoldingGroupBreakdownTable'
import { SharedTransactionTable } from '@/components/holdings/SharedTransactionTable'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { shareApi } from '@/lib/api'
import type { SharedHoldingDetail } from '@/lib/types'

export default function SharedHoldingPage({ params }: { params: { token: string; holdingId: string } }) {
  const [holding, setHolding] = useState<SharedHoldingDetail | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [loginRequired, setLoginRequired] = useState(false)

  const load = useCallback(async (initial = false) => {
    if (initial) setLoading(true); else setRefreshing(true)
    setError(''); setLoginRequired(false)
    try {
      setHolding(await shareApi.getHolding(params.token, params.holdingId))
      setLastUpdated(new Date())
    } catch (err) {
      const statusCode = (err as Error & { status?: number }).status
      if (statusCode === 401) { setError('로그인이 필요한 공유 링크입니다.'); setLoginRequired(true) }
      else if (statusCode === 404) setError('종목을 찾을 수 없습니다.')
      else setError('종목 정보를 불러오지 못했습니다.')
    } finally {
      if (initial) setLoading(false); else setRefreshing(false)
    }
  }, [params.token, params.holdingId])

  useEffect(() => { void load(true) }, [load])

  if (loading) return <PageLoader />
  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3">
        <p className="text-gray-500">{error}</p>
        {loginRequired && (
          <Link href={`/auth?returnTo=${encodeURIComponent(`/share/${params.token}/holdings/${params.holdingId}`)}`}
            className="text-sm font-medium text-brand-600 hover:text-brand-700">로그인</Link>
        )}
      </div>
    )
  }
  if (!holding) return null

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <Link href={`/share/${params.token}`} className="text-sm text-gray-400 hover:text-gray-600">공유 포트폴리오</Link>
          <span className="text-gray-300">/</span>
          <span className="text-sm text-gray-600">{holding.ticker}</span>
        </div>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="mt-1 text-xl font-semibold text-gray-900">{holding.name}</h1>
            <p className="text-sm text-gray-400">{holding.ticker} · {holding.market} · {holding.currency}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-gray-400 sm:inline">화면 갱신: {formatLastUpdated(lastUpdated)}</span>
            <Button variant="secondary" size="sm" loading={refreshing} onClick={() => void load(false)}>새로고침</Button>
          </div>
        </div>
      </div>

      <HoldingPerformanceSummary performance={holding.performance} quantity={holding.remaining_quantity} currency={holding.currency} />

      <Card>
        <h2 className="mb-4 font-semibold text-gray-900">가격 차트</h2>
        <PriceChart snapshots={holding.snapshots} currency={holding.currency} currentPrice={holding.current_price} transactions={holding.transactions} />
      </Card>

      <HoldingGroupBreakdownTable groupBreakdown={holding.group_breakdown} currency={holding.currency} />

      {holding.show_transactions && (
        <Card>
          <h2 className="mb-4 font-semibold text-gray-900">거래 내역</h2>
          <SharedTransactionTable transactions={holding.transactions} currency={holding.currency} />
        </Card>
      )}
      <p className="mt-8 text-center text-xs text-gray-300">powered by realchoi</p>
    </div>
  )
}

function formatLastUpdated(value: Date | null) {
  if (!value) return '아직 없음'
  return new Intl.DateTimeFormat('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(value)
}
