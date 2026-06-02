import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import useSWR from 'swr'
import { AddTransactionForm } from '@/components/holdings/AddTransactionForm'
import { holdingsApi } from '@/lib/api'
import type { BuyLot, Label, SourceGroup } from '@/lib/types'

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}))

jest.mock('@/lib/api', () => ({
  holdingsApi: {
    addTransaction: jest.fn(),
    listLots: jest.fn(),
  },
  fetcher: jest.fn(),
}))

const mockedUseSWR = useSWR as jest.Mock
const mockedHoldingsApi = holdingsApi as jest.Mocked<typeof holdingsApi>
const onSuccess = jest.fn()

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
]
const lots: BuyLot[] = [
  {
    id: 'lot-1',
    transaction_id: 'buy-1',
    source_group_id: null,
    label_ids: [],
    original_quantity: '5',
    remaining_quantity: '5',
    unit_price: '70000',
    transaction_date: '2024-01-01',
  },
]
const sourceLots: BuyLot[] = [
  {
    ...lots[0],
    id: 'lot-2',
    transaction_id: 'buy-2',
    source_group_id: 'source-1',
    transaction_date: '2024-02-01',
  },
]

function fillTrade(quantity = '2', price = '80000') {
  fireEvent.change(screen.getByLabelText('수량'), { target: { value: quantity } })
  fireEvent.change(screen.getByLabelText('단가'), { target: { value: price } })
}

describe('AddTransactionForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedUseSWR.mockImplementation((url: string) => ({
      data: url === '/api/groups/sources' ? sourceGroups : labels,
      isLoading: false,
    }))
    mockedHoldingsApi.listLots.mockResolvedValue(lots)
    mockedHoldingsApi.addTransaction.mockResolvedValue({ id: 'tx-1' } as never)
  })

  it('submits a default buy as unclassified with no labels or sell allocations', async () => {
    render(<AddTransactionForm holdingId="holding-1" onSuccess={onSuccess} />)
    fillTrade()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '추가' }))
    })

    expect(mockedHoldingsApi.addTransaction).toHaveBeenCalledWith(
      'holding-1',
      expect.objectContaining({
        type: 'BUY',
        source_group_id: null,
        label_ids: [],
        sell_allocations: [],
      }),
    )
  })

  it('submits selected source group and labels for a buy', async () => {
    render(<AddTransactionForm holdingId="holding-1" onSuccess={onSuccess} />)
    fillTrade()
    fireEvent.change(screen.getByLabelText('출처 그룹'), { target: { value: 'source-1' } })
    fireEvent.click(screen.getByRole('button', { name: '장기 투자' }))

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '추가' }))
    })

    expect(mockedHoldingsApi.addTransaction).toHaveBeenCalledWith(
      'holding-1',
      expect.objectContaining({
        source_group_id: 'source-1',
        label_ids: ['label-1'],
      }),
    )
  })

  it('fetches unclassified lots and submits a matching sell allocation', async () => {
    render(<AddTransactionForm holdingId="holding-1" onSuccess={onSuccess} />)
    fireEvent.click(screen.getByRole('button', { name: '매도' }))

    await waitFor(() => {
      expect(mockedHoldingsApi.listLots).toHaveBeenCalledWith('holding-1', {
        scope_kind: 'unclassified',
      })
    })
    expect(await screen.findByText('배분 합계 0 / 매도 수량 0')).toBeInTheDocument()

    fillTrade('3', '90000')
    fireEvent.change(screen.getByLabelText('2024. 01. 01. 매수 lot 배분'), { target: { value: '2' } })
    expect(screen.getByText('배분 합계 2 / 매도 수량 3')).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '추가' }))
    })
    expect(mockedHoldingsApi.addTransaction).not.toHaveBeenCalled()
    expect(screen.getByText('매도 수량과 lot 배분 합계가 일치해야 합니다.')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('2024. 01. 01. 매수 lot 배분'), { target: { value: '3' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '추가' }))
    })

    expect(mockedHoldingsApi.addTransaction).toHaveBeenCalledWith(
      'holding-1',
      expect.objectContaining({
        type: 'SELL',
        source_group_id: null,
        label_ids: [],
        sell_allocations: [{ buy_lot_id: 'lot-1', quantity: '3' }],
      }),
    )
  })

  it('accepts fixed-decimal allocations whose sum matches the sell quantity', async () => {
    mockedHoldingsApi.listLots.mockResolvedValue([
      { ...lots[0], id: 'lot-decimal-1', remaining_quantity: '0.1' },
      { ...lots[0], id: 'lot-decimal-2', remaining_quantity: '0.2', transaction_date: '2024-02-01' },
    ])
    render(<AddTransactionForm holdingId="holding-1" onSuccess={onSuccess} />)
    fireEvent.click(screen.getByRole('button', { name: '매도' }))
    fillTrade('0.3', '90000')

    fireEvent.change(await screen.findByLabelText('2024. 01. 01. 매수 lot 배분'), { target: { value: '0.1' } })
    fireEvent.change(screen.getByLabelText('2024. 02. 01. 매수 lot 배분'), { target: { value: '0.2' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '추가' }))
    })

    expect(mockedHoldingsApi.addTransaction).toHaveBeenCalledWith(
      'holding-1',
      expect.objectContaining({
        type: 'SELL',
        quantity: '0.3',
        sell_allocations: [
          { buy_lot_id: 'lot-decimal-1', quantity: '0.1' },
          { buy_lot_id: 'lot-decimal-2', quantity: '0.2' },
        ],
      }),
    )
  })

  it('uses lot ids for allocation input ids when buy dates match', async () => {
    mockedHoldingsApi.listLots.mockResolvedValue([
      { ...lots[0], id: 'lot-same-date-1' },
      { ...lots[0], id: 'lot-same-date-2', transaction_id: 'buy-2' },
    ])
    render(<AddTransactionForm holdingId="holding-1" onSuccess={onSuccess} />)
    fireEvent.click(screen.getByRole('button', { name: '매도' }))

    const allocationInputs = await screen.findAllByLabelText('2024. 01. 01. 매수 lot 배분')
    expect(allocationInputs.map((input) => input.id)).toEqual([
      'sell-lot-allocation-lot-same-date-1',
      'sell-lot-allocation-lot-same-date-2',
    ])
  })

  it('offers selected lot labels as recommendations without selecting them automatically', async () => {
    mockedHoldingsApi.listLots.mockResolvedValue([
      { ...lots[0], label_ids: ['label-1'] },
    ])
    render(<AddTransactionForm holdingId="holding-1" onSuccess={onSuccess} />)
    fireEvent.click(screen.getByRole('button', { name: '매도' }))
    fillTrade('1', '90000')
    fireEvent.change(await screen.findByLabelText('2024. 01. 01. 매수 lot 배분'), { target: { value: '1' } })

    expect(screen.getByRole('button', { name: '장기 투자' })).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(screen.getByRole('button', { name: '추천 추가: 장기 투자' }))
    expect(screen.getByRole('button', { name: '장기 투자' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('blocks submission while source and label metadata is loading', () => {
    mockedUseSWR.mockReturnValue({ data: undefined, isLoading: true })
    render(<AddTransactionForm holdingId="holding-1" onSuccess={onSuccess} />)

    expect(screen.getByRole('button', { name: '추가' })).toBeDisabled()
  })

  it('shows metadata load failures and blocks submission', () => {
    mockedUseSWR.mockReturnValue({
      data: undefined,
      error: new Error('metadata unavailable'),
      isLoading: false,
    })
    render(<AddTransactionForm holdingId="holding-1" onSuccess={onSuccess} />)

    expect(screen.getByText('출처/라벨 정보를 불러오지 못했습니다.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '추가' })).toBeDisabled()
  })

  it('keeps lots for the latest selected source when an earlier request finishes last', async () => {
    let resolveUnclassified: (lots: BuyLot[]) => void = () => {}
    let resolveSource: (lots: BuyLot[]) => void = () => {}
    mockedHoldingsApi.listLots.mockImplementation((_holdingId, scope) => (
      new Promise((resolve) => {
        if (scope.scope_kind === 'source') resolveSource = resolve
        else resolveUnclassified = resolve
      })
    ))
    render(<AddTransactionForm holdingId="holding-1" onSuccess={onSuccess} />)

    fireEvent.click(screen.getByRole('button', { name: '매도' }))
    await waitFor(() => expect(mockedHoldingsApi.listLots).toHaveBeenCalledWith('holding-1', {
      scope_kind: 'unclassified',
    }))
    fireEvent.change(screen.getByLabelText('출처 그룹'), { target: { value: 'source-1' } })
    await waitFor(() => expect(mockedHoldingsApi.listLots).toHaveBeenCalledWith('holding-1', {
      scope_kind: 'source',
      scope_id: 'source-1',
    }))

    await act(async () => resolveSource(sourceLots))
    expect(screen.getByText('2024. 02. 01. 매수')).toBeInTheDocument()

    await act(async () => resolveUnclassified(lots))
    expect(screen.getByText('2024. 02. 01. 매수')).toBeInTheDocument()
    expect(screen.queryByText('2024. 01. 01. 매수')).not.toBeInTheDocument()
  })
})
