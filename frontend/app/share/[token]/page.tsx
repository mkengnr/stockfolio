'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { GroupFilterMenu } from '@/components/dashboard/GroupFilterMenu'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import { PortfolioChart } from '@/components/dashboard/PortfolioChart'
import { PortfolioSummary } from '@/components/dashboard/PortfolioSummary'
import { ChartRangeControl, getChartVisibleDateRange, type ChartRange } from '@/components/dashboard/chartRange'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardTitle } from '@/components/ui/Card'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { shareApi } from '@/lib/api'
import { toDashboardHistoryRow, toDashboardHolding } from '@/lib/shareAdapters'
import { formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { SharedGroup, SharedTag } from '@/lib/types'

function SharedGroupView({
  group,
  onRefresh,
  isRefreshing,
  lastUpdated,
}: {
  group: SharedGroup
  onRefresh: () => void
  isRefreshing: boolean
  lastUpdated: Date | null
}) {
  const [selectedGroupKey, setSelectedGroupKey] = useState('total')
  const [chartRange, setChartRange] = useState<ChartRange>('3m')
  useEffect(() => {
    // A reloaded share may drop (or later reintroduce) the selected key;
    // reset instead of silently keeping stale state.
    if (
      selectedGroupKey !== 'total'
      && !group.dashboard.groups.some((item) => item.key === selectedGroupKey)
    ) {
      setSelectedGroupKey('total')
    }
  }, [group, selectedGroupKey])
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
  const chartVisibleRange = useMemo(
    () => getChartVisibleDateRange(selectedHistoryRows, chartRange),
    [selectedHistoryRows, chartRange],
  )
  const groupFilterOptions = useMemo(
    () => [
      { value: 'total', label: '전체' },
      ...group.dashboard.groups.map((item) => ({ value: item.key, label: item.name })),
    ],
    [group.dashboard.groups],
  )
  const groupFilterControl = group.dashboard.groups.length > 0 ? (
    <GroupFilterMenu
      value={selectedGroupKey}
      options={groupFilterOptions}
      onChange={setSelectedGroupKey}
      className="w-full sm:w-56"
    />
  ) : null

  const shareMessage = group.share_description || group.description
  return (
    <SharedLayout
      name={group.name}
      color={group.color}
      onRefresh={onRefresh}
      isRefreshing={isRefreshing}
      lastUpdated={lastUpdated}
      stickyControls={groupFilterControl}
    >
      <section className="flex flex-col gap-3">
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div>
            <h2 className="font-semibold text-gray-900">{selectedGroup?.name ?? '전체'} 수익현황</h2>
            <p className="mt-1 text-sm text-gray-500">{shareMessage || '공유된 포트폴리오 범위의 수익현황입니다.'}</p>
          </div>
        </div>
        <div aria-live="polite">
          <PortfolioSummary
            summary={selectedSummary}
            displayCurrency={group.dashboard.display_currency}
            hideZeroPrincipalMetrics
          />
        </div>
      </section>
      <Card>
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold text-gray-900">포트폴리오 변화</h2>
            <p className="mt-1 text-sm text-gray-500">평가금액, 잔여원금, 그룹 구성과 일별손익을 표시합니다.</p>
          </div>
          <ChartRangeControl value={chartRange} onChange={setChartRange} />
        </div>
        <PortfolioChart
          historyRows={selectedHistoryRows}
          compositionRows={historyRows}
          includeComposition={!selectedGroup}
          displayCurrency={group.dashboard.display_currency}
          visibleRange={chartVisibleRange}
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

function LegacySharedTagView({
  tag,
  onRefresh,
  isRefreshing,
  lastUpdated,
}: {
  tag: SharedTag
  onRefresh: () => void
  isRefreshing: boolean
  lastUpdated: Date | null
}) {
  const shareMessage = tag.share_description || tag.description
  return (
    <SharedLayout
      name={tag.name}
      color={tag.color}
      onRefresh={onRefresh}
      isRefreshing={isRefreshing}
      lastUpdated={lastUpdated}
    >
      {shareMessage && <p className="text-sm text-gray-500">{shareMessage}</p>}
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

function SharedLayout({
  name,
  color,
  onRefresh,
  isRefreshing,
  lastUpdated,
  stickyControls,
  children,
}: {
  name: string
  color: string
  onRefresh: () => void
  isRefreshing: boolean
  lastUpdated: Date | null
  stickyControls?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900">포트폴리오 공유</h1>
          <Badge color={color}>{name}</Badge>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">화면 갱신: {formatLastUpdated(lastUpdated)}</span>
          <Button type="button" variant="secondary" loading={isRefreshing} onClick={onRefresh} className="shrink-0">
            새로고침
          </Button>
        </div>
      </div>
      {stickyControls && (
        <div
          data-testid="share-sticky-toolbar"
          className="sticky top-0 z-30 -mx-4 border-y border-gray-200 bg-gray-50/95 px-4 py-3 shadow-sm backdrop-blur sm:-mx-6 sm:px-6"
        >
          {stickyControls}
        </div>
      )}
      {children}
      <p className="mt-8 text-center text-xs text-gray-300">powered by stockfolio</p>
    </div>
  )
}

export default function SharePage({ params }: { params: { token: string } }) {
  const [group, setGroup] = useState<SharedGroup | null>(null)
  const [legacyTag, setLegacyTag] = useState<SharedTag | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [loginRequired, setLoginRequired] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const load = useCallback(async (initial = false) => {
    if (initial) setLoading(true)
    else setRefreshing(true)
    setError('')
    setLoginRequired(false)
    try {
      const nextGroup = await shareApi.getGroup(params.token)
      setGroup(nextGroup)
      setLegacyTag(null)
      setLastUpdated(new Date())
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
        const nextLegacyTag = await shareApi.getLegacy(params.token)
        setLegacyTag(nextLegacyTag)
        setGroup(null)
        setLastUpdated(new Date())
      } catch (legacyError) {
        if ((legacyError as Error & { status?: number }).status === 401) {
          setError('로그인이 필요한 공유 링크입니다.')
          setLoginRequired(true)
        } else {
          setError('공유 링크를 찾을 수 없습니다.')
        }
      }
    } finally {
      if (initial) setLoading(false)
      else setRefreshing(false)
    }
  }, [params.token])

  useEffect(() => {
    void load(true)
  }, [load])

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
  if (group) return <SharedGroupView group={group} onRefresh={() => void load(false)} isRefreshing={refreshing} lastUpdated={lastUpdated} />
  if (legacyTag) return <LegacySharedTagView tag={legacyTag} onRefresh={() => void load(false)} isRefreshing={refreshing} lastUpdated={lastUpdated} />
  return null
}

function formatLastUpdated(value: Date | null) {
  if (!value) return '아직 없음'
  return new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(value)
}
