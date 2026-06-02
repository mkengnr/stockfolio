import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import SharePage from '@/app/share/[token]/page'
import { shareApi } from '@/lib/api'
import type { SharedGroup, SharedTag } from '@/lib/types'

jest.mock('@/lib/api', () => ({
  shareApi: {
    getGroup: jest.fn(),
    getLegacy: jest.fn(),
  },
}))

const mockedShareApi = shareApi as jest.Mocked<typeof shareApi>
const emptySummary = {
  currencies: {},
  holding_count: 0,
  accounting_status: 'ok' as const,
  warnings: [],
}

const sharedGroup: SharedGroup = {
  kind: 'source',
  name: '월급',
  color: '#6366f1',
  description: '급여 투자',
  summary: emptySummary,
  holdings: {
    holdings: [{
      ticker: 'AAPL',
      name: 'Apple',
      currency: 'USD',
      remaining_quantity: '2',
      remaining_cost_basis: '200',
      current_price: '120',
      current_value: '240',
      unrealized_profit_loss: '40',
    }],
    accounting_status: 'ok',
    warnings: [],
  },
  history: { series: { KRW: [], USD: [] } },
}

const legacyTag: SharedTag = {
  name: '기존 태그',
  color: '#6366f1',
  description: null,
  summary: null,
  holding_count: 0,
}

function apiError(status: number) {
  return Object.assign(new Error('failed'), { status })
}

describe('SharePage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders the shared group payload before trying the legacy endpoint', async () => {
    mockedShareApi.getGroup.mockResolvedValue(sharedGroup)
    render(<SharePage params={{ token: 'token-1' }} />)

    expect(await screen.findByText('월급')).toBeInTheDocument()
    expect(screen.getByText('Apple')).toBeInTheDocument()
    expect(mockedShareApi.getGroup).toHaveBeenCalledWith('token-1')
    expect(mockedShareApi.getLegacy).not.toHaveBeenCalled()
  })

  it('falls back to the legacy endpoint only after a 404', async () => {
    mockedShareApi.getGroup.mockRejectedValue(apiError(404))
    mockedShareApi.getLegacy.mockResolvedValue(legacyTag)
    render(<SharePage params={{ token: 'token-2' }} />)

    expect(await screen.findByText('기존 태그')).toBeInTheDocument()
    expect(mockedShareApi.getLegacy).toHaveBeenCalledWith('token-2')
  })

  it('shows login guidance and does not fall back after a 401', async () => {
    mockedShareApi.getGroup.mockRejectedValue(apiError(401))
    render(<SharePage params={{ token: 'token-3' }} />)

    await waitFor(() => {
      expect(screen.getByText('로그인이 필요한 공유 링크입니다.')).toBeInTheDocument()
    })
    expect(mockedShareApi.getLegacy).not.toHaveBeenCalled()
  })
})
