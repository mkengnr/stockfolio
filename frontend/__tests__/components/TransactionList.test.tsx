import '@testing-library/jest-dom'
import { act, fireEvent, render, screen } from '@testing-library/react'
import useSWR from 'swr'
import { TransactionList } from '@/components/holdings/TransactionList'
import { holdingsApi } from '@/lib/api'
import type { Label, SourceGroup, Transaction } from '@/lib/types'

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}))

jest.mock('@/lib/api', () => ({
  holdingsApi: {
    deleteTransaction: jest.fn(),
    updateTransactionClassification: jest.fn(),
  },
  fetcher: jest.fn(),
}))

const mockedUseSWR = useSWR as jest.Mock
const mockedHoldingsApi = holdingsApi as jest.Mocked<typeof holdingsApi>
const onRefresh = jest.fn()
const sourceGroups: SourceGroup[] = [
  {
    id: 'source-1',
    name: '연금 계좌',
    color: '#2563eb',
    description: null,
    share_token: null,
    share_requires_auth: true,
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'source-2',
    name: '일반 계좌',
    color: '#7c3aed',
    description: null,
    share_token: null,
    share_requires_auth: true,
    created_at: '2024-01-01T00:00:00Z',
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
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'label-2',
    name: '배당',
    color: '#ea580c',
    description: null,
    share_token: null,
    share_requires_auth: true,
    created_at: '2024-01-01T00:00:00Z',
  },
]
const transactions: Transaction[] = [
  {
    id: 'tx-1',
    type: 'BUY',
    quantity: '2',
    price: '70000',
    transaction_date: '2024-01-01',
    created_at: '2024-01-01T00:00:00Z',
    source_group_id: 'source-1',
    label_ids: ['label-1'],
    requires_review: true,
    buy_lot: null,
    sell_allocations: [],
  },
]
const reviewedSell: Transaction = {
  ...transactions[0],
  id: 'sell-1',
  type: 'SELL',
  requires_review: true,
}

describe('TransactionList', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedUseSWR.mockImplementation((url: string) => ({
      data: url === '/api/groups/sources' ? sourceGroups : labels,
      isLoading: false,
    }))
    mockedHoldingsApi.updateTransactionClassification.mockResolvedValue(transactions[0])
  })

  it('shows source group, labels, and requires-review badge', () => {
    render(
      <TransactionList holdingId="holding-1" transactions={transactions} currency="KRW" onRefresh={onRefresh} />,
    )

    expect(screen.getByText('연금 계좌')).toBeInTheDocument()
    expect(screen.getByText('장기 투자')).toBeInTheDocument()
    expect(screen.getByText('검토 필요')).toBeInTheDocument()
  })

  it('does not mislabel a classified transaction while source groups are loading', () => {
    mockedUseSWR.mockReturnValue({ data: undefined, isLoading: true })
    render(
      <TransactionList holdingId="holding-1" transactions={transactions} currency="KRW" onRefresh={onRefresh} />,
    )

    expect(screen.getByText('출처 확인 중')).toBeInTheDocument()
    expect(screen.queryByText('미분류')).not.toBeInTheDocument()
  })

  it('patches transaction classification and refreshes the holding', async () => {
    render(
      <TransactionList holdingId="holding-1" transactions={transactions} currency="KRW" onRefresh={onRefresh} />,
    )
    fireEvent.click(screen.getByRole('button', { name: '분류 수정' }))
    fireEvent.change(screen.getByLabelText('출처 그룹'), { target: { value: 'source-2' } })
    fireEvent.click(screen.getByRole('button', { name: '배당' }))

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '분류 저장' }))
    })

    expect(mockedHoldingsApi.updateTransactionClassification).toHaveBeenCalledWith(
      'holding-1',
      'tx-1',
      { source_group_id: 'source-2', label_ids: ['label-1', 'label-2'] },
    )
    expect(onRefresh).toHaveBeenCalled()
  })

  it('shows the API error when a transaction cannot be deleted', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true)
    mockedHoldingsApi.deleteTransaction.mockRejectedValue(new Error('Sell quantity exceeds available holding quantity'))
    render(
      <TransactionList holdingId="holding-1" transactions={transactions} currency="KRW" onRefresh={onRefresh} />,
    )

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '삭제' }))
    })

    expect(screen.getByText('Sell quantity exceeds available holding quantity')).toBeInTheDocument()
    expect(onRefresh).not.toHaveBeenCalled()
  })

  it('opens the reviewed sell repair editor for a migrated sell', () => {
    render(
      <TransactionList holdingId="holding-1" transactions={[reviewedSell]} currency="KRW" onRefresh={onRefresh} />,
    )

    fireEvent.click(screen.getByRole('button', { name: '매도 검토' }))

    expect(screen.getByRole('button', { name: '매도 검토 저장' })).toBeInTheDocument()
  })
})
