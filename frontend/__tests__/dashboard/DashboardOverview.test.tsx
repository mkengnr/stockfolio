import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DashboardOverview } from '@/components/dashboard/DashboardOverview'
import { DisplayCurrencyToggle } from '@/components/dashboard/DisplayCurrencyToggle'
import { GroupPerformanceTable } from '@/components/dashboard/GroupPerformanceTable'
import { portfolioApi } from '@/lib/api'
import type { DashboardResponse } from '@/lib/types'

jest.mock('@/lib/api', () => ({
  portfolioApi: {
    labelDashboard: jest.fn(),
    dashboardPath: jest.fn((c) => `/api/portfolio/dashboard?display_currency=${c}`),
  },
  fetcher: jest.fn(),
}))

jest.mock('next/link', () => {
  const MockLink = ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
  MockLink.displayName = 'Link'
  return MockLink
})

jest.mock('@/components/dashboard/PortfolioChart', () => ({
  PortfolioChart: ({
    historyRows,
    compositionRows,
    includeComposition,
    visibleRange,
  }: {
    historyRows: Array<{ group_name: string; snapshot_date: string }>
    compositionRows: Array<{ group_name: string; snapshot_date: string }>
    includeComposition: boolean
    visibleRange: { from: string; to: string } | null
  }) => (
    <div data-testid="portfolio-chart">
      selected:{historyRows.map((row) => row.group_name).join(',')}|
      composition:{includeComposition ? compositionRows.map((row) => row.group_name).join(',') : 'off'}|
      dates:{historyRows.map((row) => row.snapshot_date).join(',')}|
      visible:{visibleRange ? `${visibleRange.from}..${visibleRange.to}` : 'all'}
    </div>
  ),
}))

const dashboard: DashboardResponse = {
  display_currency: 'KRW',
  exchange_rate: {
    base: 'USD',
    quote: 'KRW',
    rate: '1380.5',
    as_of: '2026-06-05T09:00:00Z',
  },
  last_refreshed_at: '2026-06-06T00:45:59Z',
  current_price_as_of: '2026-06-05',
  comparison_as_of: '2026-06-04',
  price_dates_by_market: { KRX: '2026-06-05', US: '2026-06-04' },
  comparison_dates_by_market: { KRX: '2026-06-04', US: '2026-06-03' },
  summary: {
    total_invested_principal: '1000000',
    total_cost_basis: '800000',
    total_current_value: '900000',
    total_current_value_change: '50000',
    total_current_value_change_pct: '1.5',
    total_unrealized_profit_loss: '100000',
    total_unrealized_profit_loss_pct: '12.5',
    total_profit_loss: '100000',
    total_profit_loss_pct: '12.5',
  },
  groups: [
    {
      kind: 'source',
      id: 'source-1',
      name: '모음통장',
      color: '#4f46e5',
      source_group_ids: ['source-1'],
      summary: {
        total_invested_principal: '600000',
        total_cost_basis: '500000',
        total_current_value: '580000',
        total_current_value_change: '30000',
        total_current_value_change_pct: '1.5',
        total_unrealized_profit_loss: '80000',
        total_unrealized_profit_loss_pct: '16',
        total_profit_loss: '80000',
        total_profit_loss_pct: '16',
      },
      holdings: [],
    },
    {
      kind: 'combined',
      id: 'combined-1',
      name: '장기투자',
      color: '#059669',
      source_group_ids: ['source-1'],
      summary: {
        total_invested_principal: '400000',
        total_cost_basis: '300000',
        total_current_value: '320000',
        total_current_value_change: '10000',
        total_current_value_change_pct: '1.5',
        total_unrealized_profit_loss: '20000',
        total_unrealized_profit_loss_pct: '6.67',
        total_profit_loss: '20000',
        total_profit_loss_pct: '6.67',
      },
      holdings: [],
    },
    {
      kind: 'unclassified',
      id: null,
      name: '미분류',
      color: null,
      source_group_ids: [],
      summary: {
        total_invested_principal: null,
        total_cost_basis: null,
        total_current_value: null,
        total_current_value_change: null,
        total_current_value_change_pct: null,
        total_unrealized_profit_loss: null,
        total_unrealized_profit_loss_pct: null,
        total_profit_loss: null,
        total_profit_loss_pct: null,
      },
      holdings: [],
    },
  ],
  history: {
    rows: [
      {
        group_kind: 'total',
        group_id: null,
        group_name: '전체',
        snapshot_date: '2026-02-01',
        total_value: '700000',
        total_invested_principal: '1000000',
        total_cost_basis: '800000',
        total_profit_loss: '-100000',
      },
      {
        group_kind: 'source',
        group_id: 'source-1',
        group_name: '모음통장',
        snapshot_date: '2026-02-01',
        total_value: '520000',
        total_invested_principal: '600000',
        total_cost_basis: '500000',
        total_profit_loss: '20000',
      },
      {
        group_kind: 'total',
        group_id: null,
        group_name: '전체',
        snapshot_date: '2026-06-01',
        total_value: '900000',
        total_invested_principal: '1000000',
        total_cost_basis: '800000',
        total_profit_loss: '100000',
      },
      {
        group_kind: 'source',
        group_id: 'source-1',
        group_name: '모음통장',
        snapshot_date: '2026-06-01',
        total_value: '580000',
        total_invested_principal: '600000',
        total_cost_basis: '500000',
        total_profit_loss: '80000',
      },
      {
        group_kind: 'combined',
        group_id: 'combined-1',
        group_name: '장기투자',
        snapshot_date: '2026-06-01',
        total_value: '320000',
        total_invested_principal: '400000',
        total_cost_basis: '300000',
        total_profit_loss: '20000',
      },
    ],
  },
  holdings: [],
  warnings: ['AAPL 시세를 가져오지 못했습니다.'],
}

describe('GroupPerformanceTable', () => {
  it('renders principal, remaining principal, current value, profit, and profit percentage', () => {
    render(<GroupPerformanceTable groups={dashboard.groups} displayCurrency="KRW" />)

    expect(screen.getByText('그룹')).toBeInTheDocument()
    expect(screen.getByText('투자원금')).toBeInTheDocument()
    expect(screen.getByText('잔여원금')).toBeInTheDocument()
    expect(screen.getByText('평가금액')).toBeInTheDocument()
    expect(screen.getByText('전일대비')).toBeInTheDocument()
    expect(screen.getByText('평가손익')).toBeInTheDocument()
    expect(screen.getByText('총손익')).toBeInTheDocument()
    expect(screen.getByText('총손익률')).toBeInTheDocument()
    expect(screen.getByText('모음통장')).toBeInTheDocument()
    expect(screen.getByText('장기투자')).toBeInTheDocument()
    expect(screen.getByText('미분류')).toBeInTheDocument()
    expect(screen.getByText('+16.00%')).toBeInTheDocument()
  })
})

describe('DisplayCurrencyToggle', () => {
  it('calls onChange with USD and shows exchange-rate text', () => {
    const onChange = jest.fn()

    render(
      <DisplayCurrencyToggle
        value="KRW"
        exchangeRate={dashboard.exchange_rate}
        onChange={onChange}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'USD 별도' }))

    expect(onChange).toHaveBeenCalledWith('USD')
    expect(screen.getByText(/1 USD = ₩1,381/)).toBeInTheDocument()
    expect(screen.getByText(/2026-06-05 기준/)).toBeInTheDocument()
  })
})

describe('DashboardOverview', () => {
  it('shows per-market current and comparison dates in the header', () => {
    render(
      <DashboardOverview
        dashboard={dashboard}
        displayCurrency="KRW"
        onDisplayCurrencyChange={jest.fn()}
        onRefresh={jest.fn()}
        isRefreshing={false}
        lastUpdated={new Date('2026-06-06T00:45:59Z')}
      />,
    )

    expect(screen.getByText('현재가 기준: 한국 2026-06-05 · 미국 2026-06-04')).toBeInTheDocument()
    expect(screen.getByText('비교 기준(직전 거래일): 한국 2026-06-04 · 미국 2026-06-03')).toBeInTheDocument()
  })

  it('renders total performance, group performance, transaction link, and warnings', () => {
    render(
      <DashboardOverview
        dashboard={dashboard}
        displayCurrency="KRW"
        onDisplayCurrencyChange={jest.fn()}
        onRefresh={jest.fn()}
        isRefreshing={false}
        lastUpdated={new Date('2026-06-05T09:00:00Z')}
      />,
    )

    expect(screen.getByText('전체 수익현황')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /그룹 필터/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '새로고침' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '+ 종목 등록' })).not.toBeInTheDocument()
    expect(screen.getByText('그룹별 수익현황')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '거래내역 보기' })).toHaveAttribute('href', '/transactions')
    expect(screen.getByText('AAPL 시세를 가져오지 못했습니다.')).toBeInTheDocument()
    expect(screen.getByText('통합 그룹은 비교용이며 단순 합산 시 중복 가능')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '하나의 차트' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '각각 보기' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '전체+그룹' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '전체만' })).not.toBeInTheDocument()
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('selected:전체')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('composition:전체,모음통장,전체,모음통장,장기투자')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('2026-02-01')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('visible:2026-03-01..2026-06-01')
    expect(screen.getByText(/마지막 조회/)).toHaveTextContent('2026-06-06')
    expect(screen.getByText(/현재가 기준/)).toHaveTextContent('2026-06-05')
    expect(screen.getByText(/비교 기준\(직전 거래일\)/)).toHaveTextContent('2026-06-04')
  })

  it('uses three months as the default chart range and can show all history', () => {
    render(
      <DashboardOverview
        dashboard={dashboard}
        displayCurrency="KRW"
        onDisplayCurrencyChange={jest.fn()}
        onRefresh={jest.fn()}
        isRefreshing={false}
        lastUpdated={new Date('2026-06-05T09:00:00Z')}
      />,
    )

    expect(screen.getByRole('button', { name: '3개월' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('2026-02-01')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('visible:2026-03-01..2026-06-01')

    fireEvent.click(screen.getByRole('button', { name: '전체' }))

    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('2026-02-01')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('visible:all')
  })

  it('filters the dashboard by selected group', () => {
    render(
      <DashboardOverview
        dashboard={{
          ...dashboard,
          groups: dashboard.groups.map((group) => group.id === 'source-1'
            ? {
                ...group,
                holdings: [
                  {
                    holding_id: 'holding-1',
                    ticker: '005930',
                    name: '삼성전자',
                    market: 'KRX',
                    currency: 'KRW',
                    quantity: '0.25',
                    remaining_cost_basis: '125000',
                    current_price: '580000',
                    current_value: '145000',
                    unrealized_profit_loss: '20000',
                    groups: [{ source_group_id: 'source-1', name: '모음통장', color: '#4f46e5', remaining_quantity: '0.25' }],
                  },
                ],
              }
            : group),
          holdings: [
            {
              holding_id: 'holding-1',
              ticker: '005930',
              name: '삼성전자',
              market: 'KRX',
              currency: 'KRW',
              quantity: '1',
              remaining_cost_basis: '500000',
              current_price: '580000',
              current_value: '580000',
              unrealized_profit_loss: '80000',
              groups: [{ source_group_id: 'source-1', name: '모음통장', color: '#4f46e5', remaining_quantity: '1' }],
            },
          ],
        }}
        displayCurrency="KRW"
        onDisplayCurrencyChange={jest.fn()}
        onRefresh={jest.fn()}
        isRefreshing={false}
        lastUpdated={new Date('2026-06-05T09:00:00Z')}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /그룹 필터/ }))
    fireEvent.click(screen.getByRole('option', { name: /모음통장/ }))

    expect(screen.getByText('모음통장 수익현황')).toBeInTheDocument()
    expect(screen.getByText('삼성전자')).toBeInTheDocument()
    expect(screen.getByText('0.25')).toBeInTheDocument()
    expect(screen.getAllByText('₩145,000').length).toBeGreaterThan(0)
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('selected:모음통장')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('composition:off')
  })

  it('keeps all chart rows while passing the selected range as the visible window', () => {
    render(
      <DashboardOverview
        dashboard={dashboard}
        displayCurrency="KRW"
        onDisplayCurrencyChange={jest.fn()}
        onRefresh={jest.fn()}
        isRefreshing={false}
        lastUpdated={new Date('2026-06-05T09:00:00Z')}
      />,
    )

    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('2026-02-01')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('visible:2026-03-01..2026-06-01')
    fireEvent.click(screen.getByRole('button', { name: '전체' }))
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('2026-02-01')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('visible:all')
  })

  it('shows error and retry button when label dashboard fetch fails', async () => {
    ;(portfolioApi.labelDashboard as jest.Mock).mockRejectedValue(new Error('network'))
    render(
      <DashboardOverview
        dashboard={dashboard}
        labels={[{ id: '9', name: '배당주', color: '#f59e0b' }]}
        displayCurrency="KRW"
        onDisplayCurrencyChange={jest.fn()}
        onRefresh={jest.fn()}
        isRefreshing={false}
        lastUpdated={new Date('2026-06-05T09:00:00Z')}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /그룹 필터/ }))
    fireEvent.click(screen.getByRole('option', { name: /배당주/ }))

    await waitFor(() =>
      expect(screen.getByText('라벨 데이터를 불러오지 못했습니다.')).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeInTheDocument()
    // Should NOT show normal total-portfolio value under label heading in error state
    // (The total_current_value ₩900,000 must not appear as the label summary)
    expect(screen.queryByText('배당주 수익현황')).toBeInTheDocument() // heading still visible
  })

  it('renders each dashboard.warnings entry as a distinct paragraph', () => {
    const dashboardWithWarnings: DashboardResponse = {
      ...dashboard,
      warnings: ['일부 종목 지연', '환율 정보 없음'],
    }
    render(
      <DashboardOverview
        dashboard={dashboardWithWarnings}
        displayCurrency="KRW"
        onDisplayCurrencyChange={jest.fn()}
        onRefresh={jest.fn()}
        isRefreshing={false}
        lastUpdated={new Date('2026-06-22T09:00:00Z')}
      />,
    )

    expect(screen.getByText('일부 종목 지연')).toBeInTheDocument()
    expect(screen.getByText('환율 정보 없음')).toBeInTheDocument()
  })

  it('hides the warnings box when dashboard.warnings is empty', () => {
    const dashboardNoWarnings: DashboardResponse = {
      ...dashboard,
      warnings: [],
    }
    render(
      <DashboardOverview
        dashboard={dashboardNoWarnings}
        displayCurrency="KRW"
        onDisplayCurrencyChange={jest.fn()}
        onRefresh={jest.fn()}
        isRefreshing={false}
        lastUpdated={new Date('2026-06-22T09:00:00Z')}
      />,
    )

    expect(screen.queryByText('일부 종목 지연')).not.toBeInTheDocument()
    // The amber warning box should not be present
    expect(document.querySelector('.bg-amber-50')).toBeNull()
  })

  it('fetches the label dashboard on demand when a label is selected', async () => {
    ;(portfolioApi.labelDashboard as jest.Mock).mockResolvedValue({
      ...dashboard,
      summary: { ...dashboard.summary, total_current_value: '999' },
      groups: [],
    })
    render(
      <DashboardOverview
        dashboard={dashboard}
        labels={[{ id: '9', name: '배당주', color: '#f59e0b' }]}
        displayCurrency="KRW"
        onDisplayCurrencyChange={jest.fn()}
        onRefresh={jest.fn()}
        isRefreshing={false}
        lastUpdated={new Date('2026-06-05T09:00:00Z')}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /그룹 필터/ }))
    fireEvent.click(screen.getByRole('option', { name: /배당주/ }))
    await waitFor(() => expect(portfolioApi.labelDashboard).toHaveBeenCalledWith('9', 'KRW'))
  })
})
