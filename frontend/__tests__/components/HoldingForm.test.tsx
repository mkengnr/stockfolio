import '@testing-library/jest-dom'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { HoldingForm } from '@/components/holdings/HoldingForm'
import { holdingsApi } from '@/lib/api'

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), refresh: jest.fn() }),
}))

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn().mockReturnValue({ data: [], isLoading: false }),
}))

jest.mock('@/lib/api', () => ({
  holdingsApi: { create: jest.fn() },
  tagsApi: { addHolding: jest.fn() },
  stocksApi: { search: jest.fn().mockResolvedValue([]) },
  fetcher: jest.fn(),
}))

const mockedHoldingsApi = holdingsApi as jest.Mocked<typeof holdingsApi>

function fillField(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

describe('HoldingForm', () => {
  beforeEach(() => jest.clearAllMocks())

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

  it('shows no market hint for empty ticker', () => {
    render(<HoldingForm />)
    expect(screen.queryByText(/한국 주식/)).not.toBeInTheDocument()
    expect(screen.queryByText(/해외 주식/)).not.toBeInTheDocument()
  })

  it('calls holdingsApi.create on submit', async () => {
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
        }),
      )
    })
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
