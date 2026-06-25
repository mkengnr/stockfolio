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
    visibleRange,
    livePoint,
    liveComposition,
    showGainLossBand,
  }: {
    historyRows: Array<{ group_name: string; snapshot_date: string }>
    includeComposition: boolean
    visibleRange: { from: string; to: string } | null
    livePoint?: {
      snapshotDate: string | null
      groupKind: string
      groupId: string | null
      groupName: string
      summary: { total_current_value: string | null; total_current_value_change: string | null }
    } | null
    liveComposition?: Array<{
      snapshotDate: string | null
      groupKind: string
      groupId: string | null
      groupName: string
      summary: { total_current_value: string | null }
    }>
    showGainLossBand?: boolean
  }) => (
    <div data-testid="portfolio-chart">
      selected:{historyRows.map((row) => row.group_name).join(',')}|
      composition:{includeComposition ? 'on' : 'off'}|
      dates:{historyRows.map((row) => row.snapshot_date).join(',')}|
      visible:{visibleRange ? `${visibleRange.from}..${visibleRange.to}` : 'all'}|
      live:{livePoint ? `${livePoint.snapshotDate}:${livePoint.summary.total_current_value}:${livePoint.summary.total_current_value_change}:${livePoint.groupKind}:${livePoint.groupId ?? 'null'}:${livePoint.groupName}` : 'null'}|
      live-composition:{(liveComposition ?? []).map((point) => `${point.snapshotDate}:${point.summary.total_current_value}:${point.groupKind}:${point.groupId ?? 'null'}:${point.groupName}`).join(',')}|
      band:{showGainLossBand ? 'on' : 'off'}
    </div>
  ),
}))

jest.mock('@/components/dashboard/HoldingsTable', () => ({
  HoldingsTable: ({
    holdings,
    stickyTop,
  }: {
    holdings: Array<{ name: string; quantity?: string; remaining_quantity?: string }>
    stickyTop?: number
  }) => (
    <div data-testid="holdings-table" data-sticky-top={stickyTop ?? 'default'}>
      {holdings.map((holding) => (
        <div key={holding.name}>
          <span>{holding.name}</span>
          <span>{holding.quantity ?? holding.remaining_quantity}</span>
        </div>
      ))}
    </div>
  ),
}))

const mockedShareApi = shareApi as jest.Mocked<typeof shareApi>

const sharedGroup: SharedGroup = {
  kind: 'source',
  name: '월급',
  color: '#6366f1',
  description: '급여 투자',
  share_description: '함께 보는 월급 포트폴리오입니다.',
  dashboard: {
    display_currency: 'KRW',
    price_dates_by_market: { KRX: '2026-06-23', US: '2026-06-22' },
    comparison_dates_by_market: { KRX: '2026-06-20', US: '2026-06-18' },
    daily_change_active_by_market: { KRX: false, US: true },
    warnings: ['AAPL 현재가 기준일이 시장 날짜보다 미래입니다: 2026-06-23'],
    summary: {
      total_invested_principal: '300',
      total_cost_basis: '300',
      total_current_value: '390',
      total_current_value_change: '20',
      total_current_value_change_pct: '1.5',
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
        total_current_value_change_pct: '1.5',
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
        current_value_change: '10',
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
          snapshot_date: '2026-02-01',
          total_value: '320',
          total_invested_principal: '300',
          total_cost_basis: '300',
          total_profit_loss: '20',
        },
        {
          group_key: 'group-1',
          group_kind: 'source',
          group_name: '급여',
          snapshot_date: '2026-02-01',
          total_value: '210',
          total_invested_principal: '200',
          total_cost_basis: '200',
          total_profit_loss: '10',
        },
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
      current_value_change: '20',
      unrealized_profit_loss: '90',
      groups: [{ name: '급여', color: '#4f46e5', remaining_quantity: '2' }],
    }],
  },
}

const legacyTag: SharedTag = {
  name: '기존 태그',
  color: '#6366f1',
  description: null,
  share_description: null,
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
    expect(screen.getByText('함께 보는 월급 포트폴리오입니다.')).toBeInTheDocument()
    expect(screen.getByText('Apple')).toBeInTheDocument()
    expect(screen.getByText('당일손익 기준: 한국 당일 시세 없음 · 미국 2026-06-22 vs 2026-06-18')).toBeInTheDocument()
    expect(screen.getByText('AAPL 현재가 기준일이 시장 날짜보다 미래입니다: 2026-06-23')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('AAPL 현재가 기준일이 시장 날짜보다 미래입니다: 2026-06-23')
    expect(mockedShareApi.getGroup).toHaveBeenCalledWith('token-1')
    expect(mockedShareApi.getLegacy).not.toHaveBeenCalled()
  })

  it('tolerates a staggered shared payload without additive metadata', async () => {
    mockedShareApi.getGroup.mockResolvedValue({
      ...sharedGroup,
      dashboard: {
        ...sharedGroup.dashboard,
        price_dates_by_market: { KRX: '2026-06-23' },
        comparison_dates_by_market: undefined,
        daily_change_active_by_market: undefined,
        warnings: undefined,
      },
    } as unknown as SharedGroup)

    render(<SharePage params={{ token: 'token-old' }} />)

    expect(await screen.findByText('당일손익 기준: 한국 2026-06-23 기준')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('filters shared dashboard summary, chart, and holdings by a component group', async () => {
    mockedShareApi.getGroup.mockResolvedValue(sharedGroup)
    render(<SharePage params={{ token: 'token-1' }} />)

    await screen.findByRole('button', { name: /그룹 필터/ })
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('selected:전체')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('composition:on')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('dates:2026-02-01,2026-06-01')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('visible:2026-03-23..2026-06-23')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('live:2026-06-23:390:20:total:null:전체')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('live-composition:2026-06-23:240:source:group-1:급여')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('band:on')

    fireEvent.click(screen.getByRole('button', { name: /그룹 필터/ }))
    fireEvent.click(screen.getByRole('option', { name: /급여/ }))

    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('selected:급여')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('composition:off')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('live:2026-06-23:240:10:source:group-1:급여')
  })

  it('keeps history-only chart data when shared price dates are missing', async () => {
    mockedShareApi.getGroup.mockResolvedValue({
      ...sharedGroup,
      dashboard: { ...sharedGroup.dashboard, price_dates_by_market: undefined },
    })

    render(<SharePage params={{ token: 'token-no-dates' }} />)

    expect(await screen.findByTestId('portfolio-chart')).toHaveTextContent('live:null')
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('visible:2026-03-01..2026-06-01')
  })

  it('announces summary changes politely for screen readers', async () => {
    mockedShareApi.getGroup.mockResolvedValue(sharedGroup)
    const { container } = render(<SharePage params={{ token: 'token-1' }} />)

    await screen.findByRole('button', { name: /그룹 필터/ })
    const liveRegion = container.querySelector('[aria-live="polite"]')
    expect(liveRegion).not.toBeNull()
    expect(liveRegion!.textContent).toContain('평가금액')
  })

  it('resets the group filter when a reloaded share no longer has the selected group', async () => {
    mockedShareApi.getGroup.mockResolvedValueOnce(sharedGroup)
    const { rerender } = render(<SharePage params={{ token: 'token-1' }} />)
    await screen.findByRole('button', { name: /그룹 필터/ })
    fireEvent.click(screen.getByRole('button', { name: /그룹 필터/ }))
    fireEvent.click(screen.getByRole('option', { name: /급여/ }))
    expect(screen.getByTestId('portfolio-chart')).toHaveTextContent('selected:급여')

    const reloadedGroup: SharedGroup = {
      ...sharedGroup,
      dashboard: {
        ...sharedGroup.dashboard,
        groups: [{ ...sharedGroup.dashboard.groups[0], key: 'group-9', name: '새그룹' }],
      },
    }
    mockedShareApi.getGroup.mockResolvedValueOnce(reloadedGroup)
    rerender(<SharePage params={{ token: 'token-2' }} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /그룹 필터.*전체/ })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: /그룹 필터/ }))
    expect(screen.getByRole('option', { name: /새그룹/ })).toBeInTheDocument()
  })

  it('refreshes the shared group payload without leaving the share page', async () => {
    mockedShareApi.getGroup
      .mockResolvedValueOnce(sharedGroup)
      .mockResolvedValueOnce({
        ...sharedGroup,
        dashboard: {
          ...sharedGroup.dashboard,
          holdings: [{ ...sharedGroup.dashboard.holdings[0], name: 'Microsoft' }],
        },
      })
    render(<SharePage params={{ token: 'token-1' }} />)

    expect(await screen.findByText('Apple')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '새로고침' }))

    expect(await screen.findByText('Microsoft')).toBeInTheDocument()
    expect(mockedShareApi.getGroup).toHaveBeenCalledTimes(2)
    expect(mockedShareApi.getLegacy).not.toHaveBeenCalled()
  })

  it('keeps share refresh in the sticky toolbar so it stays visible on scroll', async () => {
    mockedShareApi.getGroup.mockResolvedValue(sharedGroup)
    render(<SharePage params={{ token: 'token-1' }} />)

    await screen.findByText('Apple')

    const refreshButton = screen.getByRole('button', { name: '새로고침' })
    expect(refreshButton.closest('[data-testid="share-sticky-toolbar"]')).not.toBeNull()
  })

  it('parks the shared holdings table header below the sticky share toolbar', async () => {
    mockedShareApi.getGroup.mockResolvedValue(sharedGroup)
    render(<SharePage params={{ token: 'token-1' }} />)

    const table = await screen.findByTestId('holdings-table')

    expect(table).toHaveAttribute('data-sticky-top', '70')
  })

  it('shows the sticky refresh toolbar even when there is no group filter', async () => {
    mockedShareApi.getGroup.mockRejectedValue(apiError(404))
    mockedShareApi.getLegacy.mockResolvedValue(legacyTag)
    render(<SharePage params={{ token: 'token-2' }} />)

    await screen.findByText('기존 태그')

    const refreshButton = screen.getByRole('button', { name: '새로고침' })
    expect(refreshButton.closest('[data-testid="share-sticky-toolbar"]')).not.toBeNull()
    expect(screen.queryByRole('button', { name: /그룹 필터/ })).not.toBeInTheDocument()
  })

  it('hides principal-based shared summary cards when invested principal is zero', async () => {
    mockedShareApi.getGroup.mockResolvedValue({
      ...sharedGroup,
      dashboard: {
        ...sharedGroup.dashboard,
        summary: {
          ...sharedGroup.dashboard.summary,
          total_invested_principal: '0',
          total_profit_loss: '90',
          total_profit_loss_pct: '30',
        },
      },
    })

    render(<SharePage params={{ token: 'token-1' }} />)

    await screen.findByText('Apple')

    expect(screen.queryByText('투자원금')).not.toBeInTheDocument()
    expect(screen.queryByText('총손익')).not.toBeInTheDocument()
    expect(screen.queryByText('총손익률')).not.toBeInTheDocument()
    expect(screen.getByText('잔여원금')).toBeInTheDocument()
    expect(screen.getAllByText('평가금액').length).toBeGreaterThan(0)
    expect(screen.getAllByText('당일손익').length).toBeGreaterThan(0)
    expect(screen.queryByText('전일대비')).not.toBeInTheDocument()
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
