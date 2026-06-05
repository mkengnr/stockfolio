import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { DashboardOverview } from '@/components/dashboard/DashboardOverview'
import { DisplayCurrencyToggle } from '@/components/dashboard/DisplayCurrencyToggle'
import { GroupPerformanceTable } from '@/components/dashboard/GroupPerformanceTable'
import type { DashboardResponse } from '@/lib/types'

jest.mock('next/link', () => {
  const MockLink = ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
  MockLink.displayName = 'Link'
  return MockLink
})

jest.mock('@/components/dashboard/PortfolioChart', () => ({
  PortfolioChart: () => <div>차트 렌더됨</div>,
}))

const dashboard: DashboardResponse = {
  display_currency: 'KRW',
  exchange_rate: {
    base: 'USD',
    quote: 'KRW',
    rate: '1380.5',
    as_of: '2026-06-05T09:00:00Z',
  },
  summary: {
    total_invested_principal: '1000000',
    total_cost_basis: '800000',
    total_current_value: '900000',
    total_current_value_change: '50000',
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
        total_unrealized_profit_loss: '80000',
        total_unrealized_profit_loss_pct: '16',
        total_profit_loss: '80000',
        total_profit_loss_pct: '16',
      },
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
        total_unrealized_profit_loss: '20000',
        total_unrealized_profit_loss_pct: '6.67',
        total_profit_loss: '20000',
        total_profit_loss_pct: '6.67',
      },
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
        total_unrealized_profit_loss: null,
        total_unrealized_profit_loss_pct: null,
        total_profit_loss: null,
        total_profit_loss_pct: null,
      },
    },
  ],
  history: {
    rows: [
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
    expect(screen.getByLabelText('그룹 필터')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '새로고침' })).toBeInTheDocument()
    expect(screen.getByText('그룹별 수익현황')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '거래내역 보기' })).toHaveAttribute('href', '/transactions')
    expect(screen.getByText('AAPL 시세를 가져오지 못했습니다.')).toBeInTheDocument()
    expect(screen.getByText('통합 그룹은 비교용이며 단순 합산 시 중복 가능')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '하나의 차트' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '각각 보기' })).toBeInTheDocument()
  })

  it('filters the dashboard by selected group', () => {
    render(
      <DashboardOverview
        dashboard={{
          ...dashboard,
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

    fireEvent.change(screen.getByLabelText('그룹 필터'), { target: { value: 'source:source-1' } })

    expect(screen.getByText('모음통장 수익현황')).toBeInTheDocument()
    expect(screen.getByText('삼성전자')).toBeInTheDocument()
  })
})
