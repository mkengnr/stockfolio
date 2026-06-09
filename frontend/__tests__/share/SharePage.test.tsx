import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import SharePage from '@/app/share/[token]/page'
import { shareApi } from '@/lib/api'
import type { SharedGroup, SharedTag } from '@/lib/types'

jest.mock('@/lib/api', () => ({
  shareApi: {
    getGroup: jest.fn(),
    getLegacy: jest.fn(),
  },
}))

jest.mock('@/components/dashboard/PortfolioChart', () => ({
  PortfolioChart: ({
    historyRows,
    includeComposition,
  }: {
    historyRows: Array<{ group_name: string }>
    includeComposition: boolean
  }) => (
    <div data-testid="portfolio-chart">
      selected:{historyRows.map((row) => row.group_name).join(',')}|
      composition:{includeComposition ? 'on' : 'off'}
    </div>
  ),
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
  dashboard: {
    display_currency: 'KRW',
    summary: {
      total_invested_principal: '300',
      total_cost_basis: '300',
      total_current_value: '390',
      total_current_value_change: '20',
      total_unrealized_profit_loss: '90',
      total_unrealized_profit_loss_pct: '30',
      total_profit_loss: '90',
      total_profit_loss_pct: '30',
    },
    groups: [{
      key: 'group-1',
      kind: 'source',
      name: '급여',
      color: '#4f46e5',
      summary: {
        total_invested_principal: '200',
        total_cost_basis: '200',
        total_current_value: '240',
        total_current_value_change: '10',
        total_unrealized_profit_loss: '40',
        total_unrealized_profit_loss_pct: '20',
        total_profit_loss: '40',
        total_profit_loss_pct: '20',
      },
      holdings: [{
        ticker: 'AAPL',
        name: 'Apple',
        market: 'US',
        currency: 'USD',
        quantity: '2',
        remaining_cost_basis: '200',
        current_price: '120',
        current_value: '240',
        unrealized_profit_loss: '40',
        groups: [{ name: '급여', color: '#4f46e5', remaining_quantity: '2' }],
      }],
    }],
    history: {
      rows: [
        {
          group_key: 'total',
          group_kind: 'total',
          group_name: '전체',
          snapshot_date: '2026-06-01',
          total_value: '390',
          total_invested_principal: '300',
          total_cost_basis: '300',
          total_profit_loss: '90',
        },
        {
          group_key: 'group-1',
          group_kind: 'source',
          group_name: '급여',
          snapshot_date: '2026-06-01',
          total_value: '240',
          total_invested_principal: '200',
          total_cost_basis: '200',
          total_profit_loss: '40',
        },
      ],
    },
    holdings: [{
      ticker: 'AAPL',
      name: 'Apple',
      market: 'US',
      currency: 'USD',
      quantity: '3',
      remaining_cost_basis: '300',
      current_price: '130',
      current_value: '390',
      unrealized_profit_loss: '90',
      groups: [{ name: '급여', color: '#4f46e5', remaining_quantity: '2' }],
    }],
  },
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

  it('filters shared dashboard summary, chart, and holdings by a component group', async () => {
    mockedShareApi.getGroup.mockResolvedValue(sharedGroup)
    render(<SharePage params={{ token: 'token-1' }} />)

    const filter = await screen.findByLabelText('그룹 필터')
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('selected:전체')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('composition:on')

    fireEvent.change(filter, { target: { value: 'group-1' } })

    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('selected:급여')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('composition:off')
  })

  it('falls back to the legacy endpoint only after a 404', async () => {
    mockedShareApi.getGroup.mockRejectedValue(apiError(404))
    mockedShareApi.getLegacy.mockResolvedValue(legacyTag)
    render(<SharePage params={{ token: 'token-2' }} />)

    expect(await screen.findByText('기존 태그')).toBeInTheDocument()
    expect(mockedShareApi.getLegacy).toHaveBeenCalledWith('token-2')
  })

  it('links to login with the shared page return path and does not fall back after a 401', async () => {
    mockedShareApi.getGroup.mockRejectedValue(apiError(401))
    render(<SharePage params={{ token: 'token-3' }} />)

    await waitFor(() => {
      expect(screen.getByText('로그인이 필요한 공유 링크입니다.')).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: '로그인' })).toHaveAttribute(
      'href',
      '/auth?returnTo=%2Fshare%2Ftoken-3',
    )
    expect(mockedShareApi.getLegacy).not.toHaveBeenCalled()
  })
})
