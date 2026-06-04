'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import { PortfolioChart } from '@/components/dashboard/PortfolioChart'
import { PortfolioSummary } from '@/components/dashboard/PortfolioSummary'
import { Badge } from '@/components/ui/Badge'
import { Card, CardTitle } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { shareApi } from '@/lib/api'
import { formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { SharedGroup, SharedTag } from '@/lib/types'

function SharedGroupView({ group }: { group: SharedGroup }) {
  return (
    <SharedLayout name={group.name} color={group.color} description={group.description}>
      <PortfolioSummary summary={group.summary} />
      <Card>
        <h2 className="font-semibold text-gray-900">포트폴리오 변화</h2>
        <p className="mb-4 mt-1 text-sm text-gray-500">통화별 축을 분리해 표시합니다.</p>
        <PortfolioChart series={group.history.series} />
      </Card>
      <Card noPad>
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-semibold text-gray-900">보유 종목</h2>
        </div>
        <HoldingsTable holdings={group.holdings.holdings} />
      </Card>
    </SharedLayout>
  )
}

function LegacySharedTagView({ tag }: { tag: SharedTag }) {
  return (
    <SharedLayout name={tag.name} color={tag.color} description={tag.description}>
      {tag.summary && Object.entries(tag.summary.currencies).map(([currency, currencySummary]) => (
        <div key={currency}>
          <p className="mb-2 text-xs font-semibold text-gray-400">{currency}</p>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              { label: '종목 수', value: `${currencySummary.holding_count}개` },
              { label: '투자원금', value: formatCurrency(currencySummary.total_cost_basis, currency as 'KRW' | 'USD') },
              { label: '평가금액', value: currencySummary.total_current_value ? formatCurrency(currencySummary.total_current_value, currency as 'KRW' | 'USD') : '—' },
              { label: '수익률', value: formatPercent(currencySummary.total_profit_loss_pct), colorClass: profitColor(currencySummary.total_profit_loss_pct) },
            ].map(({ label, value, colorClass }) => (
              <Card key={label}>
                <CardTitle>{label}</CardTitle>
                <p className={`mt-2 text-xl font-bold tabular-nums ${colorClass ?? 'text-gray-900'}`}>{value}</p>
              </Card>
            ))}
          </div>
        </div>
      ))}
    </SharedLayout>
  )
}

function SharedLayout({ name, color, description, children }: { name: string; color: string; description: string | null; children: React.ReactNode }) {
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-gray-900">포트폴리오 공유</h1>
        <Badge color={color}>{name}</Badge>
      </div>
      {description && <p className="text-gray-500">{description}</p>}
      {children}
      <p className="mt-8 text-center text-xs text-gray-300">powered by stockfolio</p>
    </div>
  )
}

export default function SharePage({ params }: { params: { token: string } }) {
  const [group, setGroup] = useState<SharedGroup | null>(null)
  const [legacyTag, setLegacyTag] = useState<SharedTag | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [loginRequired, setLoginRequired] = useState(false)

  useEffect(() => {
    async function load() {
      setLoading(true)
      setError('')
      setLoginRequired(false)
      try {
        setGroup(await shareApi.getGroup(params.token))
      } catch (err) {
        const status = (err as Error & { status?: number }).status
        if (status === 401) {
          setError('로그인이 필요한 공유 링크입니다.')
          setLoginRequired(true)
          return
        }
        if (status !== 404) {
          setError('공유 링크를 불러오지 못했습니다.')
          return
        }
        try {
          setLegacyTag(await shareApi.getLegacy(params.token))
        } catch (legacyError) {
          if ((legacyError as Error & { status?: number }).status === 401) {
            setError('로그인이 필요한 공유 링크입니다.')
            setLoginRequired(true)
          } else {
            setError('공유 링크를 찾을 수 없습니다.')
          }
        }
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [params.token])

  if (loading) return <PageLoader />
  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3">
        <p className="text-gray-500">{error}</p>
        {loginRequired && (
          <Link
            href={`/auth?returnTo=${encodeURIComponent(`/share/${params.token}`)}`}
            className="text-sm font-medium text-brand-600 hover:text-brand-700"
          >
            로그인
          </Link>
        )}
      </div>
    )
  }
  if (group) return <SharedGroupView group={group} />
  if (legacyTag) return <LegacySharedTagView tag={legacyTag} />
  return null
}
