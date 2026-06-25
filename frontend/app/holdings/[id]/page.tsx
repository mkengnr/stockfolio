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
import { formatCurrency, formatDate, formatPercent, profitColor } from '@/lib/utils'
import type { HoldingDetail } from '@/lib/types'
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

      <HoldingPerformanceSummary holding={holding} />

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

      <HoldingGroupBreakdownTable holding={holding} />

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

function HoldingPerformanceSummary({ holding }: { holding: HoldingDetail }) {
  const performance = holding.performance
  const cards = [
    { label: '보유수량', value: `${parseFloat(holding.quantity).toLocaleString()}주` },
    {
      label: '투자원금',
      value: performance ? formatCurrency(performance.total_invested_principal, holding.currency) : '—',
    },
    {
      label: '잔여원금',
      value: performance ? formatCurrency(performance.remaining_cost_basis, holding.currency) : '—',
    },
    {
      label: '평가금액',
      value: performance?.current_value ? formatCurrency(performance.current_value, holding.currency) : '—',
    },
    {
      label: '손익',
      value: performance?.profit_loss ? formatCurrency(performance.profit_loss, holding.currency) : '—',
      colorClass: profitColor(performance?.profit_loss ?? null),
    },
    {
      label: '손익률',
      value: formatPercent(performance?.profit_loss_pct ?? null),
      colorClass: profitColor(performance?.profit_loss_pct ?? null),
    },
  ]

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {cards.map(({ label, value, colorClass }) => (
        <Card key={label}>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</p>
          <p className={`mt-1 text-lg font-bold tabular-nums ${colorClass ?? 'text-gray-900'}`}>{value}</p>
        </Card>
      ))}
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

function HoldingGroupBreakdownTable({ holding }: { holding: HoldingDetail }) {
  if (holding.group_breakdown.length === 0) {
    return (
      <Card>
        <h2 className="font-semibold text-gray-900">그룹별 수익현황</h2>
        <p className="mt-2 text-sm text-gray-500">현재 보유 중인 그룹별 잔여 수량이 없습니다.</p>
      </Card>
    )
  }

  return (
    <Card>
      <h2 className="mb-4 font-semibold text-gray-900">그룹별 수익현황</h2>
      <div className="overflow-x-auto">
        <table className="min-w-[900px] divide-y divide-gray-100 text-sm">
          <thead>
            <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
              <th className="px-3 py-2">그룹</th>
              <th className="px-3 py-2 text-right">수량</th>
              <th className="px-3 py-2 text-right">투자원금</th>
              <th className="px-3 py-2 text-right">잔여원금</th>
              <th className="px-3 py-2 text-right">평가금액</th>
              <th className="px-3 py-2 text-right">손익</th>
              <th className="px-3 py-2 text-right">손익률</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {holding.group_breakdown.map((group) => (
              <tr key={group.source_group_id ?? 'unclassified'} className="hover:bg-gray-50">
                <td className="px-3 py-3">
                  <span className="inline-flex items-center gap-2 font-medium text-gray-900">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: group.color ?? '#9ca3af' }}
                    />
                    {group.name}
                  </span>
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {parseFloat(group.remaining_quantity).toLocaleString()}주
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {formatCurrency(group.invested_principal, holding.currency)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {formatCurrency(group.remaining_cost_basis, holding.currency)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {group.current_value ? formatCurrency(group.current_value, holding.currency) : '—'}
                </td>
                <td className={`px-3 py-3 text-right tabular-nums font-medium ${profitColor(group.profit_loss)}`}>
                  {group.profit_loss ? formatCurrency(group.profit_loss, holding.currency) : '—'}
                </td>
                <td className={`px-3 py-3 text-right tabular-nums font-medium ${profitColor(group.profit_loss_pct)}`}>
                  {formatPercent(group.profit_loss_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export default function HoldingPage({ params }: { params: { id: string } }) {
  const { id } = params
  return (
    <AuthGuard>
      <HoldingDetailContent id={id} />
    </AuthGuard>
  )
}
