'use client'

import { useEffect, useState } from 'react'
import { Card, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { shareApi } from '@/lib/api'
import { formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { SharedTag } from '@/lib/types'

function SharedPortfolioView({ tag }: { tag: SharedTag }) {
  const summary = tag.summary

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-gray-900">포트폴리오 공유</h1>
        <Badge color={tag.color}>{tag.name}</Badge>
      </div>
      {tag.description && <p className="text-gray-500">{tag.description}</p>}

      {summary && Object.entries(summary.currencies).map(([currency, currencySummary]) => (
        <div key={currency}>
          <p className="mb-2 text-xs font-semibold text-gray-400">{currency}</p>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              { label: '종목 수', value: `${currencySummary.holding_count}개` },
              { label: '투자원금', value: formatCurrency(currencySummary.total_cost_basis, currency as 'KRW' | 'USD') },
              {
                label: '평가금액',
                value: currencySummary.total_current_value
                  ? formatCurrency(currencySummary.total_current_value, currency as 'KRW' | 'USD')
                  : '—',
              },
              {
                label: '수익률',
                value: formatPercent(currencySummary.total_profit_loss_pct),
                colorClass: profitColor(currencySummary.total_profit_loss_pct),
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
        </div>
      ))}

      <p className="text-center text-xs text-gray-300 mt-8">powered by stockfolio</p>
    </div>
  )
}

export default function SharePage({ params }: { params: { token: string } }) {
  const { token } = params
  const [tag, setTag] = useState<SharedTag | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    shareApi.get(token)
      .then(setTag)
      .catch(() => setError('공유 링크를 찾을 수 없습니다.'))
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
