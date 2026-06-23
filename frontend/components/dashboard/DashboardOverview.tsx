'use client'

import { useEffect, useMemo, useState } from 'react'
import useSWR from 'swr'
import Link from 'next/link'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { DisplayCurrencyToggle } from './DisplayCurrencyToggle'
import { GroupFilterMenu } from './GroupFilterMenu'
import { GroupPerformanceTable } from './GroupPerformanceTable'
import { HoldingsTable } from './HoldingsTable'
import { PortfolioChart, type DashboardLivePoint } from './PortfolioChart'
import { PortfolioSummary } from './PortfolioSummary'
import { ChartRangeControl, getChartVisibleDateRange, type ChartRange } from './chartRange'
import { formatDailyProfitBasis } from './dailyProfitBasis'
import { portfolioApi } from '@/lib/api'
import type { DashboardGroupSummary, DashboardResponse, DisplayCurrency, Label } from '@/lib/types'

interface Props {
  dashboard: DashboardResponse
  displayCurrency: DisplayCurrency
  onDisplayCurrencyChange: (currency: DisplayCurrency) => void
  onRefresh: () => void
  isRefreshing: boolean
  lastUpdated: Date | null
  labels?: Label[]
}

export function DashboardOverview({
  dashboard,
  displayCurrency,
  onDisplayCurrencyChange,
  onRefresh,
  isRefreshing,
  lastUpdated,
  labels = [],
}: Props) {
  const [chartRange, setChartRange] = useState<ChartRange>('3m')
  const [selectedGroupKey, setSelectedGroupKey] = useState('total')
  const selectedGroup = dashboard.groups.find((group) => groupKey(group) === selectedGroupKey) ?? null

  // Only reset to 'total' when the selected key is a group key that no longer exists.
  // Do NOT reset label: keys — they aren't in dashboard.groups by design.
  useEffect(() => {
    if (
      selectedGroupKey !== 'total' &&
      !selectedGroupKey.startsWith('label:') &&
      !dashboard.groups.some((group) => groupKey(group) === selectedGroupKey)
    ) {
      setSelectedGroupKey('total')
    }
  }, [dashboard.groups, selectedGroupKey])

  // ── Label-mode SWR ──────────────────────────────────────────────────────────
  const selectedLabelId = selectedGroupKey.startsWith('label:')
    ? selectedGroupKey.slice('label:'.length)
    : null
  const { data: labelDashboard, isLoading: labelLoading, error: labelError, mutate: labelMutate } = useSWR(
    selectedLabelId ? ['label-dashboard', selectedLabelId, displayCurrency] : null,
    () => portfolioApi.labelDashboard(selectedLabelId as string, displayCurrency),
  )
  const labelMode = selectedLabelId !== null
  const activeDashboard = labelMode ? (labelError ? null : labelDashboard ?? null) : dashboard
  const activeWarnings = activeDashboard?.warnings ?? []
  const currentPriceBasis = activeDashboard
    ? formatMarketDates(activeDashboard.price_dates_by_market) || formatDashboardDate(activeDashboard.current_price_as_of)
    : '—'
  const dailyProfitBasis = activeDashboard
    ? formatDailyProfitBasis(
        activeDashboard.price_dates_by_market,
        activeDashboard.comparison_dates_by_market,
        activeDashboard.daily_change_active_by_market,
      ) || formatDashboardDate(activeDashboard.current_price_as_of)
    : '—'

  // ── Derived values (non-label) ───────────────────────────────────────────────
  const selectedName = labelMode
    ? (labels.find((l) => l.id === selectedLabelId)?.name ?? '라벨')
    : (selectedGroup?.name ?? '전체')
  const selectedSummary = selectedGroup?.summary ?? dashboard.summary
  const selectedHistoryRows = useMemo(
    () => dashboard.history.rows.filter((row) => {
      if (!selectedGroup) {
        return row.group_kind === 'total'
      }
      return row.group_kind === selectedGroup.kind && (row.group_id ?? null) === selectedGroup.id
    }),
    [dashboard.history.rows, selectedGroup],
  )
  const selectedHoldings = selectedGroup?.holdings ?? dashboard.holdings

  // ── Active values (switch to label data when in label mode) ─────────────────
  const activeSummary = labelMode ? (labelDashboard?.summary ?? null) : selectedSummary
  const activeHoldings = labelMode ? (labelDashboard?.holdings ?? []) : selectedHoldings
  const activeHistoryRows = useMemo(
    () =>
      labelMode
        ? (labelDashboard?.history.rows ?? []).filter((row) => row.group_kind === 'total')
        : selectedHistoryRows,
    [labelMode, labelDashboard, selectedHistoryRows],
  )

  const livePoint = useMemo<DashboardLivePoint | null>(() => {
    if (!activeDashboard || !activeSummary) return null
    if (labelMode) {
      return {
        snapshotDate: activeDashboard.current_price_as_of,
        groupKind: 'total',
        groupId: null,
        groupName: selectedName,
        summary: activeSummary,
      }
    }
    return {
      snapshotDate: activeDashboard.current_price_as_of,
      groupKind: selectedGroup?.kind ?? 'total',
      groupId: selectedGroup?.id ?? null,
      groupName: selectedGroup?.name ?? '전체',
      summary: activeSummary,
    }
  }, [activeDashboard, activeSummary, labelMode, selectedGroup, selectedName])
  const liveComposition = useMemo<DashboardLivePoint[]>(() => {
    if (!activeDashboard) return []
    return activeDashboard.groups.map((group) => ({
      snapshotDate: activeDashboard.current_price_as_of,
      groupKind: group.kind,
      groupId: group.id,
      groupName: group.name,
      summary: group.summary,
    }))
  }, [activeDashboard])

  const chartVisibleRange = useMemo(
    () => getChartVisibleDateRange([
      ...activeHistoryRows,
      ...(livePoint?.snapshotDate ? [{ snapshot_date: livePoint.snapshotDate }] : []),
    ], chartRange),
    [activeHistoryRows, chartRange, livePoint?.snapshotDate],
  )

  // ── Group filter options (with sections; labels in their own section) ─────────
  const groupFilterOptions = useMemo(
    () => [
      { value: 'total', label: '전체' },
      ...dashboard.groups
        .filter((g) => g.kind === 'source' || g.kind === 'unclassified')
        .map((g) => ({ value: groupKey(g), label: g.name, section: '출처 그룹' })),
      ...dashboard.groups
        .filter((g) => g.kind === 'combined')
        .map((g) => ({ value: groupKey(g), label: g.name, section: '통합 그룹' })),
      ...labels.map((label) => ({ value: `label:${label.id}`, label: label.name, section: '라벨' })),
    ],
    [dashboard.groups, labels],
  )

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">대시보드</h1>
          <p className="mt-1 text-sm text-gray-500">
            포트폴리오 전체와 그룹별 수익률을 {displayCurrency === 'KRW' ? 'KRW 환산' : 'USD 별도'} 기준으로 확인합니다.
          </p>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500">
            <span>마지막 조회: {formatDashboardDateTime(activeDashboard?.last_refreshed_at ?? null)}</span>
            <span>화면 갱신: {formatLastUpdated(lastUpdated)}</span>
            <span>현재가 기준: {currentPriceBasis}</span>
            <span>당일손익 기준: {dailyProfitBasis}</span>
          </div>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-start">
          <DisplayCurrencyToggle
            value={displayCurrency}
            exchangeRate={dashboard.exchange_rate}
            onChange={onDisplayCurrencyChange}
          />
        </div>
      </div>

      {activeWarnings.length > 0 && (
        <div role="status" className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {activeWarnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      )}

      <div className="sticky top-14 z-30 -mx-4 border-y border-gray-200 bg-gray-50/95 px-4 py-2 backdrop-blur sm:mx-0 sm:rounded-xl sm:border">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
          <GroupFilterMenu
            value={selectedGroupKey}
            options={groupFilterOptions}
            onChange={setSelectedGroupKey}
          />
          <Button type="button" variant="secondary" loading={isRefreshing} onClick={onRefresh} className="h-full whitespace-nowrap px-3 sm:px-4">
            새로고침
          </Button>
        </div>
      </div>

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="font-semibold text-gray-900">{selectedName} 수익현황</h2>
          <p className="mt-1 text-sm text-gray-500">손익은 평가손익과 총손익을 분리해서 표시합니다.</p>
        </div>
        {labelLoading && (
          <p className="text-sm text-gray-400">라벨 데이터를 불러오는 중…</p>
        )}
        {labelMode && labelError ? (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-red-500">라벨 데이터를 불러오지 못했습니다.</p>
            <Button variant="secondary" onClick={() => void labelMutate()}>다시 시도</Button>
          </div>
        ) : activeSummary ? (
          <PortfolioSummary summary={activeSummary} displayCurrency={displayCurrency} />
        ) : null}
      </section>

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="font-semibold text-gray-900">그룹별 수익현황</h2>
          <p className="mt-1 text-sm text-gray-500">통합 그룹은 비교용이며 단순 합산 시 중복 가능</p>
        </div>
        <GroupPerformanceTable groups={dashboard.groups} displayCurrency={displayCurrency} />
      </section>

      {!(labelMode && labelError) && (
        <>
          <Card>
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold text-gray-900">포트폴리오 변화</h2>
                <p className="mt-1 text-sm text-gray-500">
                  전체 선택 시 전체 흐름과 그룹별 흐름을 함께 볼 수 있습니다.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <ChartRangeControl value={chartRange} onChange={setChartRange} />
              </div>
            </div>
            <PortfolioChart
              historyRows={activeHistoryRows}
              compositionRows={dashboard.history.rows}
              includeComposition={!selectedGroup && !labelMode}
              displayCurrency={displayCurrency}
              visibleRange={chartVisibleRange}
              livePoint={livePoint}
              liveComposition={liveComposition}
              showGainLossBand
              referenceDefault="invested"
            />
          </Card>

          <Card noPad>
            <div className="border-b border-gray-100 px-6 py-4">
              <h2 className="font-semibold text-gray-900">보유 종목</h2>
            </div>
            <HoldingsTable holdings={activeHoldings} displayCurrency={displayCurrency} />
          </Card>
        </>
      )}

      <div className="flex justify-end">
        <Link href="/transactions" className="text-sm font-medium text-brand-600 hover:underline">
          거래내역 보기
        </Link>
      </div>
    </div>
  )
}

function groupKey(group: DashboardGroupSummary) {
  return `${group.kind}:${group.id ?? 'unclassified'}`
}

function formatLastUpdated(value: Date | null) {
  if (!value) return '아직 없음'
  return new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(value)
}

function formatDashboardDateTime(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-') + ' ' + [
    String(date.getHours()).padStart(2, '0'),
    String(date.getMinutes()).padStart(2, '0'),
    String(date.getSeconds()).padStart(2, '0'),
  ].join(':')
}

function formatDashboardDate(value: string | null) {
  if (!value) return '—'
  return value
}

const MARKET_LABELS: Record<string, string> = { KRX: '한국', US: '미국' }
const MARKET_ORDER = ['KRX', 'US']

function orderedMarketEntries<T>(byMarket: Record<string, T> | undefined): Array<[string, T]> {
  const rank = (market: string) => {
    const index = MARKET_ORDER.indexOf(market)
    return index === -1 ? MARKET_ORDER.length : index
  }

  return Object.entries(byMarket ?? {})
    .sort(([left], [right]) => rank(left) - rank(right) || left.localeCompare(right))
}

// "한국 2026-06-22 · 미국 2026-06-18" — empty string when there is nothing to show
// so callers can fall back to the single-date display.
function formatMarketDates(byMarket: Record<string, string> | undefined): string {
  return orderedMarketEntries(byMarket)
    .map(([market, value]) => `${MARKET_LABELS[market] ?? market} ${value}`)
    .join(' · ')
}
