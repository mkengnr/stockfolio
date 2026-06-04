import '@testing-library/jest-dom'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import useSWR from 'swr'
import { HoldingForm } from '@/components/holdings/HoldingForm'
import { holdingsApi } from '@/lib/api'

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), refresh: jest.fn() }),
}))

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}))

jest.mock('@/lib/api', () => ({
  holdingsApi: { create: jest.fn() },
  stocksApi: { search: jest.fn().mockResolvedValue([]) },
  fetcher: jest.fn(),
}))

const mockedUseSWR = useSWR as jest.Mock
const mockedHoldingsApi = holdingsApi as jest.Mocked<typeof holdingsApi>
const sourceGroups = [
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
const labels = [
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

function fillField(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

describe('HoldingForm', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedUseSWR.mockImplementation((url: string) => ({
      data: url === '/api/groups/sources' ? sourceGroups : labels,
      isLoading: false,
    }))
  })

  it('renders all required fields', () => {
    render(<HoldingForm />)
    expect(screen.getByLabelText('종목 코드 또는 종목명')).toBeInTheDocument()
    expect(screen.getByLabelText('매수 수량')).toBeInTheDocument()
    expect(screen.getByLabelText('매수 단가')).toBeInTheDocument()
    expect(screen.getByLabelText('매수일')).toBeInTheDocument()
  })

  it('detects KRX market for 6-digit ticker', async () => {
    render(<HoldingForm />)
    fillField('종목 코드 또는 종목명', '005930')
    await waitFor(() => {
      expect(screen.getByText(/한국 주식/)).toBeInTheDocument()
    })
  })

  it('detects US market for alphabetic ticker', async () => {
    render(<HoldingForm />)
    fillField('종목 코드 또는 종목명', 'AAPL')
    await waitFor(() => {
      expect(screen.getByText(/해외 주식/)).toBeInTheDocument()
    })
  })

  it('does not mislabel Korean name search as a US stock', () => {
    render(<HoldingForm />)
    fillField('종목 코드 또는 종목명', 'SK하이닉스')
    expect(screen.queryByText(/해외 주식/)).not.toBeInTheDocument()
  })

  it('blocks a Korean name from being submitted before an autocomplete result is selected', async () => {
    render(<HoldingForm />)
    fillField('종목 코드 또는 종목명', '삼성전자')
    fillField('매수 수량', '10')
    fillField('매수 단가', '75000')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '등록하기' }))
    })

    expect(mockedHoldingsApi.create).not.toHaveBeenCalled()
    expect(screen.getByText('검색 결과에서 종목을 선택하거나 유효한 종목 코드를 입력하세요.')).toBeInTheDocument()
  })

  it('shows no market hint for empty ticker', () => {
    render(<HoldingForm />)
    expect(screen.queryByText(/한국 주식/)).not.toBeInTheDocument()
    expect(screen.queryByText(/해외 주식/)).not.toBeInTheDocument()
  })

  it('submits the initial buy as unclassified with no labels by default', async () => {
    mockedHoldingsApi.create.mockResolvedValue({ id: 'new-id', tags: [] } as never)
    render(<HoldingForm />)

    fillField('종목 코드 또는 종목명', '005930')
    fillField('매수 수량', '10')
    fillField('매수 단가', '75000')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '등록하기' }))
    })

    await waitFor(() => {
      expect(mockedHoldingsApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          ticker: '005930',
          quantity: '10',
          price: '75000',
          source_group_id: null,
          label_ids: [],
        }),
      )
    })
  })

  it('submits the selected source group and labels directly with the holding', async () => {
    mockedHoldingsApi.create.mockResolvedValue({ id: 'new-id', tags: [] } as never)
    render(<HoldingForm />)

    fillField('종목 코드 또는 종목명', '005930')
    fillField('매수 수량', '10')
    fillField('매수 단가', '75000')
    fireEvent.change(screen.getByLabelText('출처 그룹'), { target: { value: 'source-1' } })
    fireEvent.click(screen.getByRole('button', { name: '장기 투자' }))

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '등록하기' }))
    })

    expect(mockedHoldingsApi.create).toHaveBeenCalledWith(
      expect.objectContaining({
        source_group_id: 'source-1',
        label_ids: ['label-1'],
      }),
    )
  })

  it('blocks submission while source and label metadata is loading', () => {
    mockedUseSWR.mockReturnValue({ data: undefined, isLoading: true })
    render(<HoldingForm />)

    expect(screen.getByRole('button', { name: '등록하기' })).toBeDisabled()
  })

  it('shows metadata load failures and blocks submission', () => {
    mockedUseSWR.mockReturnValue({
      data: undefined,
      error: new Error('metadata unavailable'),
      isLoading: false,
    })
    render(<HoldingForm />)

    expect(screen.getByText('출처/라벨 정보를 불러오지 못했습니다.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '등록하기' })).toBeDisabled()
  })

  it('shows error message on API failure', async () => {
    mockedHoldingsApi.create.mockRejectedValue(new Error('중복 종목입니다.'))
    render(<HoldingForm />)

    fillField('종목 코드 또는 종목명', '005930')
    fillField('매수 수량', '10')
    fillField('매수 단가', '75000')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '등록하기' }))
    })

    await waitFor(() => {
      expect(screen.getByText('중복 종목입니다.')).toBeInTheDocument()
    })
  })
})
