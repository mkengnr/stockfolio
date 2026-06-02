'use client'

import { useState } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import { Card, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import { fetcher, tagsApi } from '@/lib/api'
import { formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { Holding, TagDetail as TagDetailType } from '@/lib/types'

interface Props {
  tagId: string
  allHoldings: Holding[]
}

export function TagDetailView({ tagId, allHoldings }: Props) {
  const { data: tag, mutate } = useSWR<TagDetailType>(`/api/tags/${tagId}`, fetcher, {
    refreshInterval: 30_000,
  })
  const [sharingLoading, setSharingLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  if (!tag) return null

  const tagHoldings = allHoldings.filter((h) => tag.holding_ids.includes(h.id))

  async function handleShare(requiresAuth: boolean) {
    setSharingLoading(true)
    try {
      await tagsApi.enableShare(tag!.id, requiresAuth)
      await mutate()
    } finally {
      setSharingLoading(false)
    }
  }

  async function handleDisableShare() {
    setSharingLoading(true)
    try {
      await tagsApi.disableShare(tag!.id)
      await mutate()
    } finally {
      setSharingLoading(false)
    }
  }

  function copyShareUrl() {
    const url = `${window.location.origin}/share/${tag!.share_token}`
    navigator.clipboard.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const summary = tag.summary

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Badge color={tag.color} className="text-sm px-3 py-1">{tag.name}</Badge>
          {tag.description && <span className="text-sm text-gray-500">{tag.description}</span>}
        </div>
        <Link href="/" className="text-sm text-brand-600 hover:underline">← 대시보드</Link>
      </div>

      {/* Summary cards */}
      {summary && Object.entries(summary.currencies).map(([currency, currencySummary]) => (
        <div key={currency}>
          <p className="mb-2 text-xs font-semibold text-gray-400">{currency}</p>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <SummaryCards
              currency={currency as 'KRW' | 'USD'}
              summary={currencySummary}
            />
          </div>
        </div>
      ))}

      {/* Holdings */}
      <div>
        <p className="mb-3 text-sm font-medium text-gray-700">
          포함 종목 ({tagHoldings.length})
        </p>
        <HoldingsTable holdings={tagHoldings} />
      </div>

      {/* Share section */}
      <Card>
        <CardTitle>외부 공유</CardTitle>
        <div className="mt-4 flex flex-col gap-3">
          {tag.share_token ? (
            <>
              <div className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-600">
                <span className="truncate flex-1">
                  {typeof window !== 'undefined' && `${window.location.origin}/share/${tag.share_token}`}
                </span>
                <Button variant="secondary" size="sm" onClick={copyShareUrl}>
                  {copied ? '복사됨!' : '복사'}
                </Button>
              </div>
              <p className="text-xs text-gray-400">
                {tag.share_requires_auth ? '🔒 로그인 필요' : '🌐 누구나 접근 가능'}
              </p>
              <Button variant="danger" size="sm" loading={sharingLoading} onClick={handleDisableShare}>
                공유 비활성화
              </Button>
            </>
          ) : (
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" loading={sharingLoading} onClick={() => handleShare(false)}>
                공개 링크 생성 (인증 불필요)
              </Button>
              <Button variant="secondary" size="sm" loading={sharingLoading} onClick={() => handleShare(true)}>
                로그인 사용자용 링크 생성
              </Button>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

function SummaryCards({
  currency,
  summary,
}: {
  currency: 'KRW' | 'USD'
  summary: NonNullable<TagDetailType['summary']>['currencies']['KRW']
}) {
  if (!summary) return null
  return (
    <>
      <Card>
        <CardTitle>투자원금</CardTitle>
        <p className="mt-2 text-xl font-bold text-gray-900 tabular-nums">
          {formatCurrency(summary.total_cost_basis, currency)}
        </p>
      </Card>
      <Card>
        <CardTitle>평가금액</CardTitle>
        <p className="mt-2 text-xl font-bold text-gray-900 tabular-nums">
          {summary.total_current_value ? formatCurrency(summary.total_current_value, currency) : '—'}
        </p>
      </Card>
      <Card>
        <CardTitle>평가손익</CardTitle>
        <p className={`mt-2 text-xl font-bold tabular-nums ${profitColor(summary.total_profit_loss)}`}>
          {summary.total_profit_loss ? formatCurrency(summary.total_profit_loss, currency) : '—'}
        </p>
      </Card>
      <Card>
        <CardTitle>수익률</CardTitle>
        <p className={`mt-2 text-xl font-bold tabular-nums ${profitColor(summary.total_profit_loss_pct)}`}>
          {formatPercent(summary.total_profit_loss_pct)}
        </p>
      </Card>
    </>
  )
}
