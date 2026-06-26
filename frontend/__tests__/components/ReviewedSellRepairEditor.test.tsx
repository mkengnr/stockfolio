import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import useSWR from 'swr'
import { ReviewedSellRepairEditor } from '@/components/holdings/ReviewedSellRepairEditor'
import { holdingsApi } from '@/lib/api'
import type { BuyLot, Label, SourceGroup, Transaction } from '@/lib/types'

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}))

jest.mock('@/lib/api', () => ({
  holdingsApi: {
    listReviewLots: jest.fn(),
    repairReviewedSell: jest.fn(),
  },
  fetcher: jest.fn(),
}))

const mockedUseSWR = useSWR as jest.Mock
const mockedHoldingsApi = holdingsApi as jest.Mocked<typeof holdingsApi>
const onRefresh = jest.fn()
const onCancel = jest.fn()
const sourceGroups: SourceGroup[] = [{
  id: 'source-1',
  name: '가족 통장',
  color: '#2563eb',
  description: null,
  share_token: null,
  share_requires_auth: true,
  share_show_transactions: false,
  created_at: '2024-01-01T00:00:00Z',
}]
const labels: Label[] = []
const transaction: Transaction = {
  id: 'sell-1',
  type: 'SELL',
  quantity: '2',
  price: '90000',
  transaction_date: '2024-02-01',
  created_at: '2024-02-01T00:00:00Z',
  source_group_id: null,
  label_ids: [],
  requires_review: true,
  buy_lot: null,
  sell_allocations: [],
}
const lots: BuyLot[] = [{
  id: 'lot-1',
  transaction_id: 'buy-1',
  source_group_id: null,
  label_ids: [],
  original_quantity: '3',
  remaining_quantity: '3',
  unit_price: '70000',
  transaction_date: '2024-01-01',
}]

describe('ReviewedSellRepairEditor', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedUseSWR.mockImplementation((url: string) => ({
      data: url === '/api/groups/sources' ? sourceGroups : labels,
      isLoading: false,
    }))
    mockedHoldingsApi.listReviewLots.mockResolvedValue(lots)
    mockedHoldingsApi.repairReviewedSell.mockResolvedValue({ ...transaction, requires_review: false })
  })

  it('loads historical lots and saves a matching reviewed sell allocation', async () => {
    render(
      <ReviewedSellRepairEditor
        holdingId="holding-1"
        transaction={transaction}
        currency="KRW"
        onRefresh={onRefresh}
        onCancel={onCancel}
      />,
    )

    await waitFor(() => expect(mockedHoldingsApi.listReviewLots).toHaveBeenCalledWith(
      'holding-1',
      'sell-1',
      { scope_kind: 'unclassified' },
    ))
    fireEvent.change(await screen.findByLabelText('2024. 01. 01. 매수 lot 배분'), { target: { value: '2' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '매도 검토 저장' }))
    })

    expect(mockedHoldingsApi.repairReviewedSell).toHaveBeenCalledWith('holding-1', 'sell-1', {
      source_group_id: null,
      label_ids: [],
      sell_allocations: [{ buy_lot_id: 'lot-1', quantity: '2' }],
    })
    expect(onRefresh).toHaveBeenCalled()
    expect(onCancel).toHaveBeenCalled()
  })
})
