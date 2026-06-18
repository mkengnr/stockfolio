import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { PortfolioSummary } from '@/components/dashboard/PortfolioSummary'
import type { DashboardSummary, Holding, PortfolioSummary as PortfolioSummaryPayload } from '@/lib/types'

const makeHolding = (overrides: Partial<Holding> = {}): Holding => ({
  id: '1',
  ticker: '005930',
  market: 'KRX',
  name: '삼성전자',
  quantity: '10',
  avg_price: '70000',
  currency: 'KRW',
  first_buy_date: '2024-01-01',
  notes: null,
  is_active: true,
  created_at: '2024-01-01T00:00:00Z',
  current_price: '75000',
  current_value: '750000',
  profit_loss: '50000',
  profit_loss_pct: '7.14',
  cost_basis: '700000',
  ...overrides,
})

describe('PortfolioSummary', () => {
  const scopedSummary: PortfolioSummaryPayload = {
    currencies: {
      KRW: {
        total_invested_principal: '600000',
        total_cost_basis: '700000',
        total_current_value: '750000',
        total_profit_loss: '150000',
        total_profit_loss_pct: '25',
        holding_count: 1,
      },
      USD: {
        total_invested_principal: '80',
        total_cost_basis: '100',
        total_current_value: '120',
        total_profit_loss: '40',
        total_profit_loss_pct: '50',
        holding_count: 1,
      },
    },
    holding_count: 2,
    accounting_status: 'ok',
    warnings: [],
  }

  it('renders scoped remaining cost, current value, and profit without mixing currencies', () => {
    render(<PortfolioSummary summary={scopedSummary} />)

    expect(screen.getAllByText('투자원금')).toHaveLength(2)
    expect(screen.getAllByText('잔여원금')).toHaveLength(2)
    expect(screen.getAllByText('평가금액')).toHaveLength(2)
    expect(screen.getAllByText('평가손익')).toHaveLength(2)
    expect(screen.getByText(/\$80/)).toBeInTheDocument()
    expect(screen.getByText(/700,000/)).toBeInTheDocument()
  })

  it('shows scoped data quality warnings', () => {
    render(<PortfolioSummary summary={{ ...scopedSummary, warnings: ['Current price unavailable for AAPL'] }} />)

    expect(screen.getByText('Current price unavailable for AAPL')).toBeInTheDocument()
  })

  it('renders four summary cards', () => {
    render(<PortfolioSummary holdings={[makeHolding()]} />)
    expect(screen.getByText('총 투자원금')).toBeInTheDocument()
    expect(screen.getByText('총 평가금액')).toBeInTheDocument()
    expect(screen.getByText('평가손익')).toBeInTheDocument()
    expect(screen.getByText('수익률')).toBeInTheDocument()
  })

  it('shows — for value when no current_price', () => {
    render(
      <PortfolioSummary
        holdings={[makeHolding({ current_price: null, current_value: null, profit_loss: null, profit_loss_pct: null })]}
      />,
    )
    // At least one — should appear
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('renders empty holdings without crash', () => {
    render(<PortfolioSummary holdings={[]} />)
    expect(screen.getByText('총 투자원금')).toBeInTheDocument()
  })

  it('aggregates multiple holdings', () => {
    const h1 = makeHolding({ cost_basis: '700000', current_value: '750000' })
    const h2 = makeHolding({
      id: '2',
      ticker: '000660',
      name: 'SK하이닉스',
      cost_basis: '300000',
      current_value: '320000',
    })
    render(<PortfolioSummary holdings={[h1, h2]} />)
    // Total cost = 1,000,000 → should appear in formatted form
    expect(screen.getByText(/1,000,000/)).toBeInTheDocument()
  })

  it('skips inactive holdings in calculation', () => {
    const active = makeHolding({ cost_basis: '100000', current_value: '110000' })
    const inactive = makeHolding({
      id: '2',
      is_active: false,
      cost_basis: '999999',
      current_value: '888888',
    })
    render(<PortfolioSummary holdings={[active, inactive]} />)
    // Should show 100,000 for cost, not 1,099,999
    expect(screen.getByText(/100,000/)).toBeInTheDocument()
  })

  it('keeps KRW and USD summaries separate', () => {
    const krw = makeHolding({ cost_basis: '700000', current_value: '750000' })
    const usd = makeHolding({
      id: '2',
      ticker: 'AAPL',
      market: 'US',
      currency: 'USD',
      cost_basis: '100',
      current_value: '120',
    })
    render(<PortfolioSummary holdings={[krw, usd]} />)

    expect(screen.getByText('KRW')).toBeInTheDocument()
    expect(screen.getByText('USD')).toBeInTheDocument()
    expect(screen.getByText(/700,000/)).toBeInTheDocument()
    expect(screen.getByText(/\$100/)).toBeInTheDocument()
  })

  it('keeps long dashboard money values on one line', () => {
    const summary: DashboardSummary = {
      total_invested_principal: '53339320',
      total_cost_basis: '50881120',
      total_current_value: '72788995',
      total_current_value_change: '-6598515',
      total_current_value_change_pct: '-8.31',
      total_unrealized_profit_loss: '21907875',
      total_unrealized_profit_loss_pct: '43.06',
      total_profit_loss: '19449675',
      total_profit_loss_pct: '36.46',
    }

    render(<PortfolioSummary summary={summary} displayCurrency="KRW" />)

    expect(screen.getByText('-₩6,598,515')).toHaveClass('whitespace-nowrap')
  })

  it('shows a daily-change percentage under the 전일대비 card', () => {
    const summary: DashboardSummary = {
      total_invested_principal: '600000',
      total_cost_basis: '700000',
      total_current_value: '750000',
      total_current_value_change: '15000',
      total_current_value_change_pct: '2.04',
      total_unrealized_profit_loss: '50000',
      total_unrealized_profit_loss_pct: '7.14',
      total_profit_loss: '150000',
      total_profit_loss_pct: '25',
    }

    render(<PortfolioSummary summary={summary} displayCurrency="KRW" />)

    expect(screen.getByText('전일대비')).toBeInTheDocument()
    expect(screen.getByText('+2.04%')).toBeInTheDocument()
  })
})
