import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'
import { HoldingsTable } from '@/components/dashboard/HoldingsTable'
import type { Holding } from '@/lib/types'

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

  it('shows positive P&L in green', () => {
    render(<HoldingsTable holdings={[makeHolding({ profit_loss_pct: '7.14' })]} />)
    const pctCell = screen.getByText('+7.14%')
    expect(pctCell).toHaveClass('text-green-600')
  })

  it('shows negative P&L in red', () => {
    render(<HoldingsTable holdings={[makeHolding({ profit_loss_pct: '-3.50' })]} />)
    const pctCell = screen.getByText('-3.50%')
    expect(pctCell).toHaveClass('text-red-500')
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
})
