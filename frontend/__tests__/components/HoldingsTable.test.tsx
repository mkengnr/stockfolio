import '@testing-library/jest-dom'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import type { DashboardHoldingRow, Holding, PublicScopedPortfolioHolding, ScopedPortfolioHolding } from '@/lib/types'

// next/link is a server component wrapper — mock it for tests
jest.mock('next/link', () => {
  const MockLink = ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
  MockLink.displayName = 'Link'
  return MockLink
})

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

describe('HoldingsTable', () => {
  function visibleRowNames() {
    return screen
      .getAllByRole('row')
      .slice(1)
      .filter((row) => within(row).queryByRole('link'))
      .map((row) => within(row).getByRole('link').querySelector('span')?.textContent)
  }

  it('renders a scoped public holding without exposing a detail link', () => {
    const scopedHolding: PublicScopedPortfolioHolding = {
      ticker: 'AAPL',
      name: 'Apple',
      currency: 'USD',
      remaining_quantity: '2',
      remaining_cost_basis: '200',
      current_price: '120',
      current_value: '240',
      unrealized_profit_loss: '40',
    }

    render(<HoldingsTable holdings={[scopedHolding]} />)

    expect(screen.getByText('Apple')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Apple/ })).not.toBeInTheDocument()
    expect(screen.getAllByText('$40.00').length).toBeGreaterThan(0)
  })

  it('links an authenticated scoped holding to its detail page', () => {
    const scopedHolding: ScopedPortfolioHolding = {
      holding_id: 'holding-1',
      ticker: 'AAPL',
      name: 'Apple',
      currency: 'USD',
      remaining_quantity: '2',
      remaining_cost_basis: '200',
      current_price: '120',
      current_value: '240',
      unrealized_profit_loss: '40',
    }

    render(<HoldingsTable holdings={[scopedHolding]} />)

    expect(screen.getByRole('link', { name: /Apple/ })).toHaveAttribute('href', '/holdings/holding-1')
  })

  it('renders dashboard holding group badges with remaining quantities', () => {
    const dashboardHolding: DashboardHoldingRow = {
      holding_id: 'holding-1',
      ticker: 'AAPL',
      name: 'Apple',
      market: 'US',
      currency: 'USD',
      quantity: '5',
      remaining_cost_basis: '500',
      current_price: '120',
      current_value: '600',
      current_value_change: '15',
      unrealized_profit_loss: '100',
      groups: [
        { source_group_id: 'source-1', name: '모음통장', color: '#4f46e5', remaining_quantity: '3' },
        { source_group_id: null, name: '미분류', color: null, remaining_quantity: '2' },
      ],
    }

    render(<HoldingsTable holdings={[dashboardHolding]} displayCurrency="USD" />)

    expect(screen.getByText('그룹')).toBeInTheDocument()
    expect(screen.getByText('모음통장 3주')).toBeInTheDocument()
    expect(screen.getByText('미분류 2주')).toBeInTheDocument()
  })

  it('formats dashboard converted values with the selected display currency', () => {
    const dashboardHolding: DashboardHoldingRow = {
      holding_id: 'holding-1',
      ticker: 'AAPL',
      name: 'Apple',
      market: 'US',
      currency: 'USD',
      quantity: '5',
      remaining_cost_basis: '650000',
      current_price: '120',
      current_value: '780000',
      current_value_change: '-13000',
      unrealized_profit_loss: '130000',
      groups: [],
    }

    render(<HoldingsTable holdings={[dashboardHolding]} displayCurrency="KRW" />)

    expect(screen.getByText('$120.00')).toBeInTheDocument()
    expect(screen.getAllByText('₩780,000').length).toBeGreaterThan(0)
    expect(screen.queryByText('$780,000.00')).not.toBeInTheDocument()
  })

  it('renders holding daily change and a total row', () => {
    const holdings = [
      makeHolding({
        id: '1',
        name: '삼성전자',
        current_value: '750000',
        cost_basis: '700000',
        profit_loss: '50000',
      }),
      makeHolding({
        id: '2',
        name: 'SK하이닉스',
        ticker: '000660',
        current_value: '320000',
        cost_basis: '300000',
        profit_loss: '20000',
      }),
    ]
    const dashboardRows: DashboardHoldingRow[] = holdings.map((holding, index) => ({
      holding_id: holding.id,
      ticker: holding.ticker,
      name: holding.name,
      market: holding.market,
      currency: holding.currency,
      quantity: holding.quantity,
      remaining_cost_basis: holding.cost_basis,
      current_price: holding.current_price,
      current_value: holding.current_value,
      current_value_change: index === 0 ? '10000' : '-5000',
      unrealized_profit_loss: holding.profit_loss,
      groups: [],
    }))

    render(<HoldingsTable holdings={dashboardRows} displayCurrency="KRW" />)

    expect(screen.getByText('당일손익')).toBeInTheDocument()
    expect(screen.queryByText('전일대비')).not.toBeInTheDocument()
    expect(screen.getByText('+₩10,000')).toBeInTheDocument()
    expect(screen.getByText('합계')).toBeInTheDocument()
    expect(screen.getByText('+₩5,000')).toBeInTheDocument()
    expect(screen.getByText('₩1,070,000')).toBeInTheDocument()
    expect(screen.getByText('+7.00%')).toBeInTheDocument()
  })

  it('renders remaining principal as the 원금 column', () => {
    render(<HoldingsTable holdings={[makeHolding()]} />)

    expect(screen.getByText('원금')).toBeInTheDocument()
    expect(screen.getAllByText('₩700,000').length).toBeGreaterThan(0)
  })

  it('renders empty state with link when no holdings', () => {
    render(<HoldingsTable holdings={[]} />)
    expect(screen.getByText('보유 종목이 없습니다.')).toBeInTheDocument()
    expect(screen.getByText('첫 종목 등록하기 →')).toBeInTheDocument()
  })

  it('renders holding name and ticker', () => {
    render(<HoldingsTable holdings={[makeHolding()]} />)
    expect(screen.getByText('삼성전자')).toBeInTheDocument()
    expect(screen.getByText(/005930/)).toBeInTheDocument()
  })

  it('keeps the sticky holding name column compact on mobile', () => {
    render(<HoldingsTable holdings={[makeHolding({ name: '아주긴종목명이있는삼성전자우선주' })]} />)

    expect(screen.getByText(/^종목/).closest('th')).toHaveClass('w-[9rem]')
    expect(screen.getByText('아주긴종목명이있는삼성전자우선주')).toHaveClass('truncate')
    expect(screen.getByText(/005930/).closest('td')).toHaveClass('max-w-[9rem]')
  })

  it('renders — for null current_price', () => {
    render(<HoldingsTable holdings={[makeHolding({ current_price: null })]} />)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('renders multiple holdings', () => {
    const holdings = [
      makeHolding({ id: '1', name: '삼성전자', ticker: '005930' }),
      makeHolding({ id: '2', name: 'SK하이닉스', ticker: '000660' }),
    ]
    render(<HoldingsTable holdings={holdings} />)
    expect(screen.getByText('삼성전자')).toBeInTheDocument()
    expect(screen.getByText('SK하이닉스')).toBeInTheDocument()
  })

  it('links to holding detail page', () => {
    render(<HoldingsTable holdings={[makeHolding({ id: 'abc123' })]} />)
    const link = screen.getByRole('link', { name: /삼성전자/ })
    expect(link).toHaveAttribute('href', '/holdings/abc123')
  })

  it('shows positive P&L in red (Korean convention)', () => {
    render(<HoldingsTable holdings={[makeHolding({ profit_loss_pct: '7.14' })]} />)
    const pctCell = screen.getAllByText('+7.14%')[0]
    expect(pctCell).toHaveClass('text-red-500')
  })

  it('shows negative P&L in blue (Korean convention)', () => {
    render(<HoldingsTable holdings={[makeHolding({ profit_loss_pct: '-3.50' })]} />)
    const pctCell = screen.getAllByText('-3.50%')[0]
    expect(pctCell).toHaveClass('text-blue-500')
  })

  it('re-renders without crash when name column header clicked', () => {
    const holdings = [
      makeHolding({ id: '1', name: '카카오', ticker: '035720', profit_loss_pct: '5.00' }),
      makeHolding({ id: '2', name: '삼성전자', ticker: '005930', profit_loss_pct: '2.00' }),
    ]
    render(<HoldingsTable holdings={holdings} />)
    // Click name header twice (asc then desc) — just verify no crash
    fireEvent.click(screen.getByText(/^종목/))
    expect(screen.getByText('삼성전자')).toBeInTheDocument()
    expect(screen.getByText('카카오')).toBeInTheDocument()

    fireEvent.click(screen.getByText(/^종목/))
    expect(screen.getByText('삼성전자')).toBeInTheDocument()
  })

  it('sorts every holding table column from its header', () => {
    const holdings: DashboardHoldingRow[] = [
      {
        holding_id: '1',
        name: '카카오',
        ticker: '035720',
        market: 'KRX',
        currency: 'KRW',
        quantity: '3',
        remaining_cost_basis: '150000',
        current_price: '51000',
        current_value: '153000',
        current_value_change: '-1000',
        unrealized_profit_loss: '3000',
        groups: [],
      },
      {
        holding_id: '2',
        name: '삼성전자',
        ticker: '005930',
        market: 'KRX',
        currency: 'KRW',
        quantity: '1',
        remaining_cost_basis: '70000',
        current_price: '73000',
        current_value: '73000',
        current_value_change: '5000',
        unrealized_profit_loss: '3000',
        groups: [],
      },
    ]
    render(<HoldingsTable holdings={holdings} />)

    fireEvent.click(screen.getByRole('button', { name: /수량/ }))
    expect(visibleRowNames()).toEqual(['삼성전자', '카카오'])

    fireEvent.click(screen.getByRole('button', { name: /평균매수가/ }))
    expect(visibleRowNames()).toEqual(['카카오', '삼성전자'])

    fireEvent.click(screen.getByRole('button', { name: /원금/ }))
    expect(visibleRowNames()).toEqual(['삼성전자', '카카오'])

    fireEvent.click(screen.getByRole('button', { name: /현재가/ }))
    expect(visibleRowNames()).toEqual(['카카오', '삼성전자'])

    fireEvent.click(screen.getByRole('button', { name: /당일손익/ }))
    expect(visibleRowNames()).toEqual(['삼성전자', '카카오'])
  })

  it('uses custom holdingHref when provided', () => {
    const holdings = [{
      holding_id: 'abc', ticker: '005930', name: '삼성전자', market: 'KRX', currency: 'KRW',
      quantity: '10', remaining_cost_basis: '1000', current_price: '150',
      current_value: '1500', unrealized_profit_loss: '500', groups: [],
    }]
    render(<HoldingsTable holdings={holdings as any} holdingHref={(id) => `/share/T/holdings/${id}`} />)
    expect(screen.getByText('삼성전자').closest('a')).toHaveAttribute('href', '/share/T/holdings/abc')
  })

  it('does not vertically stick the native header (the floating clone owns the sticky offset) while keeping the first column horizontally sticky', () => {
    render(<HoldingsTable holdings={[makeHolding()]} />)

    const nameHeader = screen.getByRole('button', { name: /종목/ }).closest('th')
    const quantityHeader = screen.getByRole('button', { name: /수량/ }).closest('th')

    // The native <thead> must not vertically stick at top:0 — that header hides under
    // the sticky page toolbar and collides with the JS clone (which parks at stickyTop),
    // producing a doubled/peeking header during scroll. The clone is the only vertical sticky.
    expect(nameHeader).not.toHaveClass('top-0')
    expect(quantityHeader).not.toHaveClass('top-0')
    // The first column must still pin horizontally so 종목 stays visible during horizontal scroll.
    expect(nameHeader).toHaveClass('left-0')
  })
})
