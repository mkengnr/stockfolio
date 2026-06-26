'use client'

import useSWR from 'swr'
import Link from 'next/link'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { PriceChart } from '@/components/holdings/PriceChart'
import { TransactionList } from '@/components/holdings/TransactionList'
import { AddTransactionForm } from '@/components/holdings/AddTransactionForm'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { fetcher, holdingsApi } from '@/lib/api'
import type { HoldingDetail } from '@/lib/types'
import { HoldingPerformanceSummary } from '@/components/holdings/HoldingPerformanceSummary'
import { HoldingGroupBreakdownTable } from '@/components/holdings/HoldingGroupBreakdownTable'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { useRouter } from 'next/navigation'

function HoldingDetailContent({ id }: { id: string }) {
  const router = useRouter()
  const { data: holding, isLoading, isValidating, mutate } = useSWR<HoldingDetail>(
    `/api/holdings/${id}`,
    fetcher,
    { refreshInterval: 30_000 },
  )
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  useEffect(() => {
    if (holding) setLastUpdated(new Date())
  }, [holding])

  if (isLoading || !holding) return <PageLoader />

  async function handleDelete() {
    if (!confirm(`${holding!.name} 종목을 목록에서 숨기시겠습니까? 거래 내역은 유지됩니다.`)) return
    setDeleting(true)
    setDeleteError('')
    try {
      await holdingsApi.delete(holding!.id)
      router.replace('/')
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : '종목을 삭제하지 못했습니다.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">대시보드</Link>
            <span className="text-gray-300">/</span>
            <span className="text-sm text-gray-600">{holding.name}</span>
          </div>
          <h1 className="mt-1 text-xl font-semibold text-gray-900">{holding.name}</h1>
          <p className="text-sm text-gray-400">{holding.ticker} · {holding.market} · {holding.currency}</p>
          <p className="mt-1 text-xs text-gray-400">마지막 갱신: {formatLastUpdated(lastUpdated)}</p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
          <Button variant="secondary" size="sm" loading={isValidating} onClick={() => void mutate()} className="w-full sm:w-auto">
            새로고침
          </Button>
          <Button variant="danger" size="sm" loading={deleting} onClick={handleDelete} className="w-full sm:w-auto">
            종목 삭제
          </Button>
        </div>
      </div>
      {deleteError && <p className="text-sm text-red-500">{deleteError}</p>}

      <HoldingPerformanceSummary performance={holding.performance} quantity={holding.quantity} currency={holding.currency} />

      {/* Price chart */}
      <Card>
        <h2 className="mb-4 font-semibold text-gray-900">가격 차트</h2>
        <PriceChart
          snapshots={holding.snapshots}
          currency={holding.currency}
          currentPrice={holding.current_price}
          transactions={holding.transactions}
        />
      </Card>

      <HoldingGroupBreakdownTable groupBreakdown={holding.group_breakdown} currency={holding.currency} />

      {/* Transactions */}
      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">거래 내역</h2>
        </div>
        <div className="mb-6">
          <AddTransactionForm holdingId={holding.id} currency={holding.currency} onSuccess={() => mutate()} />
        </div>
        <TransactionList
          holdingId={holding.id}
          transactions={holding.transactions}
          currency={holding.currency}
          onRefresh={() => mutate()}
        />
      </Card>
    </div>
  )
}

function formatLastUpdated(value: Date | null) {
  if (!value) return '아직 없음'
  return new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(value)
}

export default function HoldingPage({ params }: { params: { id: string } }) {
  const { id } = params
  return (
    <AuthGuard>
      <HoldingDetailContent id={id} />
    </AuthGuard>
  )
}
