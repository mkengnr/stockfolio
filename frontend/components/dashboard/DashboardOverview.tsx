'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { DisplayCurrencyToggle } from './DisplayCurrencyToggle'
import { GroupPerformanceTable } from './GroupPerformanceTable'
import { HoldingsTable } from './HoldingsTable'
import { PortfolioChart } from './PortfolioChart'
import { PortfolioSummary } from './PortfolioSummary'
import { ChartRangeControl, filterHistoryRowsByChartRange, type ChartRange } from './chartRange'
import type { DashboardGroupSummary, DashboardResponse, DisplayCurrency } from '@/lib/types'

interface Props {
  dashboard: DashboardResponse
  displayCurrency: DisplayCurrency
  onDisplayCurrencyChange: (currency: DisplayCurrency) => void
  onRefresh: () => void
  isRefreshing: boolean
  lastUpdated: Date | null
}

export function DashboardOverview({
  dashboard,
  displayCurrency,
  onDisplayCurrencyChange,
  onRefresh,
  isRefreshing,
  lastUpdated,
}: Props) {
  const [chartRange, setChartRange] = useState<ChartRange>('3m')
  const [selectedGroupKey, setSelectedGroupKey] = useState('total')
  const selectedGroup = dashboard.groups.find((group) => groupKey(group) === selectedGroupKey) ?? null
  useEffect(() => {
    if (selectedGroupKey !== 'total' && !dashboard.groups.some((group) => groupKey(group) === selectedGroupKey)) {
      setSelectedGroupKey('total')
    }
  }, [dashboard.groups, selectedGroupKey])
  const selectedName = selectedGroup?.name ?? '전체'
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
  const chartHistoryRows = useMemo(
    () => filterHistoryRowsByChartRange(selectedHistoryRows, chartRange),
    [selectedHistoryRows, chartRange],
  )
  const compositionHistoryRows = useMemo(
    () => filterHistoryRowsByChartRange(dashboard.history.rows, chartRange),
    [dashboard.history.rows, chartRange],
  )
  const selectedHoldings = selectedGroup?.holdings ?? dashboard.holdings

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">대시보드</h1>
          <p className="mt-1 text-sm text-gray-500">
            포트폴리오 전체와 그룹별 수익률을 {displayCurrency === 'KRW' ? 'KRW 환산' : 'USD 별도'} 기준으로 확인합니다.
          </p>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500">
            <span>마지막 조회: {formatDashboardDateTime(dashboard.last_refreshed_at)}</span>
            <span>화면 갱신: {formatLastUpdated(lastUpdated)}</span>
            <span>현재가 기준: {formatDashboardDate(dashboard.current_price_as_of)}</span>
            <span>비교 기준(직전 거래일): {formatDashboardDate(dashboard.comparison_as_of)}</span>
          </div>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-start">
          <DisplayCurrencyToggle
            value={displayCurrency}
            exchangeRate={dashboard.exchange_rate}
            onChange={onDisplayCurrencyChange}
          />
          <Button type="button" variant="secondary" loading={isRefreshing} onClick={onRefresh} className="w-full sm:w-auto">
            새로고침
          </Button>
          <Link href="/holdings/new" className="inline-flex w-full items-center justify-center rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-600 sm:w-auto">
            + 종목 등록
          </Link>
        </div>
      </div>

      {dashboard.warnings.length > 0 && (
        <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {dashboard.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      )}

      <div className="sticky top-14 z-30 -mx-4 border-y border-gray-200 bg-gray-50/95 px-4 py-2 backdrop-blur sm:mx-0 sm:rounded-xl sm:border">
        <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <span className="shrink-0">그룹 필터</span>
          <select
            value={selectedGroupKey}
            onChange={(event) => setSelectedGroupKey(event.target.value)}
            className="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 sm:flex-none sm:min-w-48"
          >
            <option value="total">전체</option>
            {dashboard.groups.map((group) => (
              <option key={groupKey(group)} value={groupKey(group)}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="font-semibold text-gray-900">{selectedName} 수익현황</h2>
          <p className="mt-1 text-sm text-gray-500">손익은 평가손익과 총손익을 분리해서 표시합니다.</p>
        </div>
        <PortfolioSummary summary={selectedSummary} displayCurrency={displayCurrency} />
      </section>

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="font-semibold text-gray-900">그룹별 수익현황</h2>
          <p className="mt-1 text-sm text-gray-500">통합 그룹은 비교용이며 단순 합산 시 중복 가능</p>
        </div>
        <GroupPerformanceTable groups={dashboard.groups} displayCurrency={displayCurrency} />
      </section>

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
          historyRows={chartHistoryRows}
          compositionRows={compositionHistoryRows}
          includeComposition={!selectedGroup}
          displayCurrency={displayCurrency}
        />
      </Card>

      <Card noPad>
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-semibold text-gray-900">보유 종목</h2>
        </div>
        <HoldingsTable holdings={selectedHoldings} displayCurrency={displayCurrency} />
      </Card>

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
