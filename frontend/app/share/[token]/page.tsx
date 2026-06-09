'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import { PortfolioChart } from '@/components/dashboard/PortfolioChart'
import { PortfolioSummary } from '@/components/dashboard/PortfolioSummary'
import { Badge } from '@/components/ui/Badge'
import { Card, CardTitle } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { shareApi } from '@/lib/api'
import { formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { DashboardHistoryRow, DashboardHoldingRow, SharedDashboardHolding, SharedGroup, SharedTag } from '@/lib/types'

function SharedGroupView({ group }: { group: SharedGroup }) {
  const [selectedGroupKey, setSelectedGroupKey] = useState('total')
  const selectedGroup = group.dashboard.groups.find((item) => item.key === selectedGroupKey) ?? null
  const selectedSummary = selectedGroup?.summary ?? group.dashboard.summary
  const selectedHoldings = useMemo(
    () => (selectedGroup?.holdings ?? group.dashboard.holdings).map(toDashboardHolding),
    [group.dashboard.holdings, selectedGroup],
  )
  const historyRows = useMemo(
    () => group.dashboard.history.rows.map(toDashboardHistoryRow),
    [group.dashboard.history.rows],
  )
  const selectedHistoryRows = historyRows.filter((row) => (
    selectedGroup ? row.group_id === selectedGroup.key : row.group_kind === 'total'
  ))

  return (
    <SharedLayout name={group.name} color={group.color} description={group.description}>
      <section className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="font-semibold text-gray-900">{selectedGroup?.name ?? '전체'} 수익현황</h2>
            <p className="mt-1 text-sm text-gray-500">공유된 포트폴리오 범위의 수익현황입니다.</p>
          </div>
          {group.dashboard.groups.length > 0 && (
            <label className="flex flex-col gap-1 text-sm font-medium text-gray-700">
              그룹 필터
              <select
                value={selectedGroupKey}
                onChange={(event) => setSelectedGroupKey(event.target.value)}
                className="min-w-48 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900"
              >
                <option value="total">전체</option>
                {group.dashboard.groups.map((item) => (
                  <option key={item.key} value={item.key}>{item.name}</option>
                ))}
              </select>
            </label>
          )}
        </div>
        <PortfolioSummary summary={selectedSummary} displayCurrency={group.dashboard.display_currency} />
      </section>
      <Card>
        <h2 className="font-semibold text-gray-900">포트폴리오 변화</h2>
        <p className="mb-4 mt-1 text-sm text-gray-500">평가금액, 투자원금, 그룹 구성과 일별손익을 표시합니다.</p>
        <PortfolioChart
          historyRows={selectedHistoryRows}
          compositionRows={historyRows}
          includeComposition={!selectedGroup}
          displayCurrency={group.dashboard.display_currency}
        />
      </Card>
      <Card noPad>
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-semibold text-gray-900">보유 종목</h2>
        </div>
        <HoldingsTable holdings={selectedHoldings} displayCurrency={group.dashboard.display_currency} />
      </Card>
    </SharedLayout>
  )
}

function toDashboardHistoryRow(row: SharedGroup['dashboard']['history']['rows'][number]): DashboardHistoryRow {
  return {
    group_kind: row.group_kind,
    group_id: row.group_key === 'total' ? null : row.group_key,
    group_name: row.group_name,
    snapshot_date: row.snapshot_date,
    total_value: row.total_value,
    total_invested_principal: row.total_invested_principal,
    total_cost_basis: row.total_cost_basis,
    total_profit_loss: row.total_profit_loss,
  }
}

function toDashboardHolding(holding: SharedDashboardHolding): DashboardHoldingRow {
  return {
    holding_id: '',
    ticker: holding.ticker,
    name: holding.name,
    market: holding.market,
    currency: holding.currency,
    quantity: holding.quantity,
    remaining_cost_basis: holding.remaining_cost_basis,
    current_price: holding.current_price,
    current_value: holding.current_value,
    unrealized_profit_loss: holding.unrealized_profit_loss,
    groups: holding.groups.map((badge) => ({ ...badge, source_group_id: null })),
  }
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
