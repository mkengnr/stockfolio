import '@testing-library/jest-dom'
import { act, fireEvent, render, screen } from '@testing-library/react'
import useSWR from 'swr'
import TransactionsPage from '@/app/transactions/page'
import { Navbar } from '@/components/layout/Navbar'
import { transactionsApi } from '@/lib/api'
import type { Label, SourceGroup, TransactionListPayload } from '@/lib/types'

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}))

jest.mock('next/link', () => {
  const MockLink = ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
  MockLink.displayName = 'Link'
  return MockLink
})

jest.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ replace: jest.fn() }),
}))

jest.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'user-1', email: 'test@example.com', is_admin: false },
    isLoading: false,
    isAuthenticated: true,
    mutate: jest.fn(),
  }),
}))

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api')
  return {
    ...actual,
    transactionsApi: {
      listPath: jest.fn(actual.transactionsApi?.listPath),
      update: jest.fn(),
      delete: jest.fn(),
    },
  }
})

const mockedUseSWR = useSWR as jest.Mock
const mockedTransactionsApi = transactionsApi as jest.Mocked<typeof transactionsApi>
const mutateTransactions = jest.fn()

const payload: TransactionListPayload = {
  transactions: [
    {
      id: 'tx-1',
      holding_id: 'holding-1',
      ticker: '005930',
      holding_name: '삼성전자',
      currency: 'KRW',
      type: 'BUY',
      transaction_date: '2026-06-01',
      quantity: '10',
      price: '70000',
      amount: '700000',
      principal_flow: 'DEPOSIT',
      source_group_id: 'source-1',
      source_group_name: '연금 계좌',
      label_ids: ['label-1'],
      label_names: ['장기 투자'],
      requires_review: false,
      created_at: '2026-06-01T00:00:00Z',
    },
    {
      id: 'tx-2',
      holding_id: 'holding-2',
      ticker: 'AAPL',
      holding_name: 'Apple',
      currency: 'USD',
      type: 'SELL',
      transaction_date: '2026-05-20',
      quantity: '1',
      price: '190',
      amount: '190',
      principal_flow: 'WITHDRAW',
      source_group_id: null,
      source_group_name: null,
      label_ids: [],
      label_names: [],
      requires_review: true,
      created_at: '2026-05-20T00:00:00Z',
    },
  ],
}

const sourceGroups: SourceGroup[] = [
  {
    id: 'source-1',
    name: '연금 계좌',
    color: '#2563eb',
    description: null,
    share_token: null,
    share_requires_auth: true,
    share_show_transactions: false,
    created_at: '2026-01-01T00:00:00Z',
  },
]

const labels: Label[] = [
  {
    id: 'label-1',
    name: '장기 투자',
    color: '#16a34a',
    description: null,
    share_token: null,
    share_requires_auth: true,
    share_show_transactions: false,
    created_at: '2026-01-01T00:00:00Z',
  },
]

function mockSWR() {
  mockedUseSWR.mockImplementation((url: string) => {
    if (url === '/api/groups/sources') return { data: sourceGroups, isLoading: false }
    if (url === '/api/groups/labels') return { data: labels, isLoading: false }
    return { data: payload, error: undefined, isLoading: false, mutate: mutateTransactions }
  })
}

describe('TransactionsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mutateTransactions.mockResolvedValue(undefined)
    mockedTransactionsApi.delete.mockResolvedValue(undefined)
    mockedTransactionsApi.update.mockResolvedValue(payload.transactions[0])
    mockedTransactionsApi.listPath.mockImplementation((filters = {}) => {
      const params = new URLSearchParams()
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
      })
      const query = params.toString()
      return query ? `/api/transactions?${query}` : '/api/transactions'
    })
    mockSWR()
  })

  it('renders heading, table columns, and sample rows', () => {
    render(<TransactionsPage />)

    expect(screen.getByRole('heading', { name: '전체 거래내역' })).toBeInTheDocument()
    ;['주문일', '종목', '주문', '그룹', '투자원금처리', '수량', '단가', '금액', '라벨', '상태', '작업'].forEach(
      (column) => expect(screen.getByText(column)).toBeInTheDocument(),
    )
    expect(screen.getByText('삼성전자')).toBeInTheDocument()
    expect(screen.getByText('005930')).toBeInTheDocument()
    expect(screen.getByText('₩700,000')).toBeInTheDocument()
    expect(screen.getAllByText('$190.00').length).toBeGreaterThan(0)
    expect(screen.getAllByText('검토 필요').length).toBeGreaterThan(0)
  })

  it('applies filter inputs to the transactions query path', () => {
    render(<TransactionsPage />)

    fireEvent.change(screen.getByLabelText('검색어'), { target: { value: '삼성' } })
    fireEvent.change(screen.getByLabelText('주문 필터'), { target: { value: 'BUY' } })
    fireEvent.change(screen.getByLabelText('투자원금처리 필터'), { target: { value: 'DEPOSIT' } })
    fireEvent.change(screen.getByLabelText('검토 상태'), { target: { value: 'true' } })
    fireEvent.click(screen.getByRole('button', { name: '필터 적용' }))

    expect(mockedTransactionsApi.listPath).toHaveBeenLastCalledWith({
      q: '삼성',
      type: 'BUY',
      principal_flow: 'DEPOSIT',
      requires_review: 'true',
    })
  })

  it('opens the edit panel with principal flow controls', () => {
    render(<TransactionsPage />)

    fireEvent.click(screen.getAllByRole('button', { name: '수정' })[0])

    expect(screen.getByRole('heading', { name: '거래 수정' })).toBeInTheDocument()
    expect(screen.getByLabelText('투자원금처리')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '저장' })).toBeInTheDocument()
  })

  it('limits principal flow options by transaction type', () => {
    render(<TransactionsPage />)

    fireEvent.click(screen.getAllByRole('button', { name: '수정' })[1])

    const principalFlow = screen.getByLabelText('투자원금처리')
    expect(principalFlow).not.toHaveTextContent('입금')
    expect(principalFlow).toHaveTextContent('재투자')
    expect(principalFlow).toHaveTextContent('출금')
    expect(screen.getByLabelText('수량')).toBeDisabled()
  })

  it('resets the edit panel when selecting another transaction', () => {
    render(<TransactionsPage />)

    fireEvent.click(screen.getAllByRole('button', { name: '수정' })[0])
    fireEvent.change(screen.getByLabelText('단가'), { target: { value: '71000' } })

    fireEvent.click(screen.getAllByRole('button', { name: '수정' })[1])

    expect(screen.getByLabelText('단가')).toHaveValue(190)
    expect(screen.getByLabelText('수량')).toHaveValue(1)
    expect(screen.getByLabelText('투자원금처리')).toHaveValue('WITHDRAW')
  })

  it('deletes a transaction and refreshes the list', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true)
    render(<TransactionsPage />)

    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: '삭제' })[0])
    })

    expect(mockedTransactionsApi.delete).toHaveBeenCalledWith('tx-1')
    expect(mutateTransactions).toHaveBeenCalled()
  })

  it('does not delete a transaction when confirmation is cancelled', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(false)
    render(<TransactionsPage />)

    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: '삭제' })[0])
    })

    expect(mockedTransactionsApi.delete).not.toHaveBeenCalled()
    expect(mutateTransactions).not.toHaveBeenCalled()
  })
})

describe('Navbar', () => {
  it('links to the full transactions page', () => {
    render(<Navbar />)

    expect(screen.getByRole('link', { name: '거래내역' })).toHaveAttribute('href', '/transactions')
  })
})
