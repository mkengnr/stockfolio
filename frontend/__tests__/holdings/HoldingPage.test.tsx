import '@testing-library/jest-dom'
import { act, fireEvent, render, screen } from '@testing-library/react'
import useSWR from 'swr'
import HoldingPage from '@/app/holdings/[id]/page'
import { holdingsApi } from '@/lib/api'
import type { HoldingDetail } from '@/lib/types'

const replace = jest.fn()

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}))

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
}))

jest.mock('@/lib/api', () => ({
  fetcher: jest.fn(),
  holdingsApi: {
    delete: jest.fn(),
  },
}))

jest.mock('@/components/layout/AuthGuard', () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

jest.mock('@/components/holdings/PriceChart', () => ({
  PriceChart: () => null,
}))

jest.mock('@/components/holdings/AddTransactionForm', () => ({
  AddTransactionForm: () => null,
}))

jest.mock('@/components/holdings/TransactionList', () => ({
  TransactionList: () => null,
}))

const mockedUseSWR = useSWR as jest.Mock
const mockedHoldingsApi = holdingsApi as jest.Mocked<typeof holdingsApi>
const holding: HoldingDetail = {
  id: 'holding-1',
  ticker: 'AAPL',
  market: 'US',
  name: 'Apple',
  quantity: '2',
  avg_price: '100',
  currency: 'USD',
  first_buy_date: '2024-01-01',
  notes: null,
  is_active: true,
  created_at: '2024-01-01T00:00:00Z',
  current_price: '120',
  current_value: '240',
  profit_loss: '40',
  profit_loss_pct: '20',
  cost_basis: '200',
  transactions: [],
  snapshots: [],
  tags: [],
}

describe('HoldingPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedUseSWR.mockReturnValue({ data: holding, isLoading: false, mutate: jest.fn() })
  })

  it('explains that delete hides the holding and surfaces API errors', async () => {
    const confirm = jest.spyOn(window, 'confirm').mockReturnValue(true)
    mockedHoldingsApi.delete.mockRejectedValue(new Error('Holding with remaining lots cannot be deleted'))
    render(<HoldingPage params={{ id: 'holding-1' }} />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '종목 삭제' }))
    })

    expect(confirm).toHaveBeenCalledWith('Apple 종목을 목록에서 숨기시겠습니까? 거래 내역은 유지됩니다.')
    expect(screen.getByText('Holding with remaining lots cannot be deleted')).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })
})
