import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import SharedHoldingPage from '@/app/share/[token]/holdings/[holdingId]/page'
import { shareApi } from '@/lib/api'

jest.mock('@/lib/api')
jest.mock('@/components/holdings/PriceChart', () => ({ PriceChart: () => <div data-testid="price-chart" /> }))

const base = {
  ticker: '005930', name: '삼성전자', market: 'KRX', currency: 'KRW',
  remaining_quantity: '10', current_price: '150',
  performance: null, group_breakdown: [], snapshots: [],
}

function apiError(status: number) {
  return Object.assign(new Error('failed'), { status })
}

it('renders read-only detail without delete or add-transaction controls', async () => {
  ;(shareApi.getHolding as jest.Mock).mockResolvedValue({ ...base, show_transactions: false, transactions: [] })
  render(<SharedHoldingPage params={{ token: 'T', holdingId: 'H' }} />)
  await screen.findByText('삼성전자')
  expect(screen.queryByText('종목 삭제')).toBeNull()
  expect(screen.queryByText('거래 추가')).toBeNull()
  expect(screen.queryByText('거래 내역')).toBeNull()
})

it('shows transactions section when show_transactions is true', async () => {
  ;(shareApi.getHolding as jest.Mock).mockResolvedValue({
    ...base, show_transactions: true,
    transactions: [{ type: 'BUY', transaction_date: '2026-01-01', quantity: '10', price: '100' }],
  })
  render(<SharedHoldingPage params={{ token: 'T', holdingId: 'H' }} />)
  await screen.findByText('거래 내역')
  expect(screen.getByText('매수')).toBeInTheDocument()
})

it('shows a login link when the shared link requires authentication (401)', async () => {
  ;(shareApi.getHolding as jest.Mock).mockRejectedValue(apiError(401))
  render(<SharedHoldingPage params={{ token: 'T', holdingId: 'H' }} />)
  const link = await screen.findByText('로그인')
  expect(link).toHaveAttribute('href', expect.stringContaining('/auth?returnTo='))
})

it('shows a not-found message when the holding is missing (404)', async () => {
  ;(shareApi.getHolding as jest.Mock).mockRejectedValue(apiError(404))
  render(<SharedHoldingPage params={{ token: 'T', holdingId: 'H' }} />)
  expect(await screen.findByText('종목을 찾을 수 없습니다.')).toBeInTheDocument()
})
