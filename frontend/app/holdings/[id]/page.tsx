'use client'

import useSWR from 'swr'
import Link from 'next/link'
import { use } from 'react'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { PriceChart } from '@/components/holdings/PriceChart'
import { TransactionList } from '@/components/holdings/TransactionList'
import { AddTransactionForm } from '@/components/holdings/AddTransactionForm'
import { Card } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { fetcher, holdingsApi } from '@/lib/api'
import { formatCurrency, formatDate, formatPercent, profitColor } from '@/lib/utils'
import type { HoldingDetail } from '@/lib/types'
import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { useRouter } from 'next/navigation'

function HoldingDetailContent({ id }: { id: string }) {
  const router = useRouter()
  const { data: holding, isLoading, mutate } = useSWR<HoldingDetail>(
    `/api/holdings/${id}`,
    fetcher,
    { refreshInterval: 30_000 },
  )
  const [deleting, setDeleting] = useState(false)

  if (isLoading || !holding) return <PageLoader />

  async function handleDelete() {
    if (!confirm(`${holding!.name} 종목을 삭제하시겠습니까? 거래 내역도 함께 삭제됩니다.`)) return
    setDeleting(true)
    try {
      await holdingsApi.delete(holding!.id)
      router.replace('/')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Link href="/" className="text-sm text-gray-400 hover:text-gray-600">대시보드</Link>
            <span className="text-gray-300">/</span>
            <span className="text-sm text-gray-600">{holding.name}</span>
          </div>
          <h1 className="mt-1 text-xl font-semibold text-gray-900">{holding.name}</h1>
          <p className="text-sm text-gray-400">{holding.ticker} · {holding.market} · {holding.currency}</p>
        </div>
        <Button variant="danger" size="sm" loading={deleting} onClick={handleDelete}>
          종목 삭제
        </Button>
      </div>

      {/* P&L Summary */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: '수량', value: `${parseFloat(holding.quantity).toLocaleString()}주` },
          { label: '평균매수가', value: formatCurrency(holding.avg_price, holding.currency) },
          { label: '현재가', value: holding.current_price ? formatCurrency(holding.current_price, holding.currency) : '—' },
          {
            label: '수익률',
            value: formatPercent(holding.profit_loss_pct),
            colorClass: profitColor(holding.profit_loss_pct),
          },
        ].map(({ label, value, colorClass }) => (
          <Card key={label}>
            <p className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</p>
            <p className={`mt-1 text-lg font-bold tabular-nums ${colorClass ?? 'text-gray-900'}`}>{value}</p>
          </Card>
        ))}
      </div>

      {/* Price chart */}
      <Card>
        <h2 className="mb-4 font-semibold text-gray-900">가격 차트</h2>
        <PriceChart snapshots={holding.snapshots} currency={holding.currency} />
      </Card>

      {/* Transactions */}
      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">거래 내역</h2>
        </div>
        <div className="mb-6">
          <AddTransactionForm holdingId={holding.id} onSuccess={() => mutate()} />
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

export default function HoldingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <AuthGuard>
      <HoldingDetailContent id={id} />
    </AuthGuard>
  )
}
