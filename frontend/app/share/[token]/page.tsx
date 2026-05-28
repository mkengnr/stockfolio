'use client'

import { use, useEffect, useState } from 'react'
import { Card, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { shareApi } from '@/lib/api'
import { formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { Holding, TagDetail } from '@/lib/types'

function SharedPortfolioView({ tag }: { tag: TagDetail }) {
  const currency = tag.summary?.total_cost_basis
    ? 'KRW'  // simplified: assume KRW for shared views
    : 'KRW'

  // Build minimal Holding objects for the table from the tag's holding_ids
  // (shared view doesn't expose full holding data per-item for privacy)
  // The actual holdings are not returned — we show the summary only
  const summary = tag.summary

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-gray-900">포트폴리오 공유</h1>
        <Badge color={tag.color}>{tag.name}</Badge>
      </div>
      {tag.description && <p className="text-gray-500">{tag.description}</p>}

      {summary && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            { label: '종목 수', value: `${summary.holding_count}개` },
            { label: '투자원금', value: formatCurrency(summary.total_cost_basis, 'KRW') },
            {
              label: '평가금액',
              value: summary.total_current_value
                ? formatCurrency(summary.total_current_value, 'KRW')
                : '—',
            },
            {
              label: '수익률',
              value: formatPercent(summary.total_profit_loss_pct),
              colorClass: profitColor(summary.total_profit_loss_pct),
            },
          ].map(({ label, value, colorClass }) => (
            <Card key={label}>
              <CardTitle>{label}</CardTitle>
              <p className={`mt-2 text-xl font-bold tabular-nums ${colorClass ?? 'text-gray-900'}`}>
                {value}
              </p>
            </Card>
          ))}
        </div>
      )}

      <p className="text-center text-xs text-gray-300 mt-8">powered by stockfolio</p>
    </div>
  )
}

export default function SharePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params)
  const [tag, setTag] = useState<TagDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    shareApi.get(token)
      .then(setTag)
      .catch((err) => setError(err.message ?? '공유 링크를 찾을 수 없습니다.'))
      .finally(() => setLoading(false))
  }, [token])

  if (loading) return <PageLoader />
  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-gray-500">{error}</p>
      </div>
    )
  }
  if (!tag) return null

  return <SharedPortfolioView tag={tag} />
}
