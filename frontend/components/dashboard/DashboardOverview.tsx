'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Card } from '@/components/ui/Card'
import { DisplayCurrencyToggle } from './DisplayCurrencyToggle'
import { DashboardChartControls, type DashboardChartMetric, type DashboardChartView } from './DashboardChartControls'
import { GroupPerformanceTable } from './GroupPerformanceTable'
import { HoldingsTable } from './HoldingsTable'
import { PortfolioChart } from './PortfolioChart'
import { PortfolioSummary } from './PortfolioSummary'
import type { DashboardResponse, DisplayCurrency } from '@/lib/types'

interface Props {
  dashboard: DashboardResponse
  displayCurrency: DisplayCurrency
  onDisplayCurrencyChange: (currency: DisplayCurrency) => void
}

export function DashboardOverview({ dashboard, displayCurrency, onDisplayCurrencyChange }: Props) {
  const [chartMetric, setChartMetric] = useState<DashboardChartMetric>('value')
  const [chartView, setChartView] = useState<DashboardChartView>('combined')

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">대시보드</h1>
          <p className="mt-1 text-sm text-gray-500">
            포트폴리오 전체와 그룹별 수익률을 {displayCurrency === 'KRW' ? 'KRW 환산' : 'USD 별도'} 기준으로 확인합니다.
          </p>
        </div>
        <div className="flex flex-wrap items-start gap-3">
          <DisplayCurrencyToggle
            value={displayCurrency}
            exchangeRate={dashboard.exchange_rate}
            onChange={onDisplayCurrencyChange}
          />
          <Link href="/holdings/new" className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-600">
            + 종목 등록
          </Link>
        </div>
      </div>

      {dashboard.warnings.length > 0 && (
        <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {dashboard.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="font-semibold text-gray-900">전체 수익현황</h2>
        <PortfolioSummary summary={dashboard.summary} displayCurrency={displayCurrency} />
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
              선택한 표시 통화 기준의 aggregate history를 단일 축으로 표시합니다.
            </p>
          </div>
          <DashboardChartControls
            metric={chartMetric}
            view={chartView}
            onMetricChange={setChartMetric}
            onViewChange={setChartView}
          />
        </div>
        <PortfolioChart
          historyRows={dashboard.history.rows}
          displayCurrency={displayCurrency}
          metric={chartMetric}
          view={chartView}
        />
      </Card>

      <Card noPad>
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-semibold text-gray-900">보유 종목</h2>
        </div>
        <HoldingsTable holdings={dashboard.holdings} displayCurrency={displayCurrency} />
      </Card>

      <div className="flex justify-end">
        <Link href="/transactions" className="text-sm font-medium text-brand-600 hover:underline">
          거래내역 보기
        </Link>
      </div>
    </div>
  )
}
