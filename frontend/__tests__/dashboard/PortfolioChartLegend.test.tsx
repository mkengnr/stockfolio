import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import { PortfolioChart } from '@/components/dashboard/PortfolioChart'
import type { DashboardHistoryRow } from '@/lib/types'

const timeScaleApis: Array<{
  fitContent: jest.Mock
  setVisibleRange: jest.Mock
  subscribeVisibleTimeRangeChange: jest.Mock
  unsubscribeVisibleTimeRangeChange: jest.Mock
  subscribeVisibleLogicalRangeChange: jest.Mock
  setVisibleLogicalRange: jest.Mock
}> = []
const histogramSeriesApis: Array<{ setData: jest.Mock }> = []
const createChart = jest.fn(() => {
  const timeScaleApi = {
      fitContent: jest.fn(),
      setVisibleRange: jest.fn(),
      subscribeVisibleTimeRangeChange: jest.fn(),
      unsubscribeVisibleTimeRangeChange: jest.fn(),
      subscribeVisibleLogicalRangeChange: jest.fn(),
      setVisibleLogicalRange: jest.fn(),
  }
  timeScaleApis.push(timeScaleApi)
  return {
    addHistogramSeries: jest.fn(() => {
      const series = { setData: jest.fn() }
      histogramSeriesApis.push(series)
      return series
    }),
    addLineSeries: jest.fn(() => ({ setData: jest.fn() })),
    timeScale: jest.fn(() => timeScaleApi),
    applyOptions: jest.fn(),
    remove: jest.fn(),
  }
})

jest.mock('lightweight-charts', () => ({
  createChart,
  ColorType: { Solid: 'solid' },
  LineStyle: { Solid: 0, Dashed: 2 },
}))

const totalRows: DashboardHistoryRow[] = [
  {
    group_kind: 'total',
    group_id: null,
    group_name: '전체',
    snapshot_date: '2026-06-01',
    total_value: '750000',
    total_invested_principal: '600000',
    total_cost_basis: '700000',
    total_profit_loss: '50000',
  },
  {
    group_kind: 'total',
    group_id: null,
    group_name: '전체',
    snapshot_date: '2026-06-02',
    total_value: '760000',
    total_invested_principal: '600000',
    total_cost_basis: '700000',
    total_profit_loss: '60000',
  },
]

describe('DashboardPortfolioChart legend', () => {
  beforeEach(() => {
    createChart.mockClear()
    timeScaleApis.length = 0
    histogramSeriesApis.length = 0
  })

  it('omits 일별손익 from the top legend while keeping the lower panel header', () => {
    render(
      <PortfolioChart
        historyRows={totalRows}
        compositionRows={totalRows}
        includeComposition
        displayCurrency="KRW"
        visibleRange={null}
      />,
    )

    expect(screen.getAllByText('일별손익')).toHaveLength(1)
    expect(screen.getByText('평가금액')).toBeInTheDocument()
    expect(screen.getByText('잔여원금')).toBeInTheDocument()
  })

  it('does not stretch the logical range after fitting content', async () => {
    render(
      <PortfolioChart
        historyRows={totalRows}
        compositionRows={totalRows}
        includeComposition
        displayCurrency="KRW"
        visibleRange={null}
      />,
    )

    await screen.findByText('평가금액')

    await waitFor(() => {
      expect(timeScaleApis.some((api) => api.fitContent.mock.calls.length > 0)).toBe(true)
    })
    expect(timeScaleApis.some((api) => api.setVisibleLogicalRange.mock.calls.length > 0)).toBe(false)
  })

  it('keeps every daily-profit date as histogram data, including first-date whitespace', async () => {
    render(
      <PortfolioChart
        historyRows={totalRows}
        compositionRows={totalRows}
        includeComposition
        displayCurrency="KRW"
        visibleRange={null}
      />,
    )

    await waitFor(() => {
      expect(histogramSeriesApis).toHaveLength(1)
      expect(histogramSeriesApis[0].setData).toHaveBeenCalled()
    })
    expect(histogramSeriesApis[0].setData).toHaveBeenCalledWith([
      { time: '2026-06-01' },
      { time: '2026-06-02', value: 10000, color: '#dc2626' },
    ])
  })

  it('shows the upper time scale and synchronizes guarded visible time ranges with cleanup', async () => {
    const { unmount } = render(
      <PortfolioChart
        historyRows={totalRows}
        compositionRows={totalRows}
        includeComposition
        displayCurrency="KRW"
        visibleRange={null}
      />,
    )

    await waitFor(() => {
      expect(createChart).toHaveBeenCalledTimes(2)
      expect(timeScaleApis).toHaveLength(2)
      expect(timeScaleApis.every((api) => api.subscribeVisibleTimeRangeChange.mock.calls.length === 1)).toBe(true)
    })

    expect(createChart.mock.calls[0][1].timeScale.visible).toBe(true)
    expect(createChart.mock.calls[0][1].timeScale.rightOffset).toBe(
      createChart.mock.calls[1][1].timeScale.rightOffset,
    )
    expect(timeScaleApis.every((api) => api.subscribeVisibleLogicalRangeChange.mock.calls.length === 0)).toBe(true)
    expect(timeScaleApis.every((api) => api.setVisibleLogicalRange.mock.calls.length === 0)).toBe(true)

    const handlers = timeScaleApis.map(
      (api) => api.subscribeVisibleTimeRangeChange.mock.calls[0][0],
    )
    unmount()

    expect(timeScaleApis[0].unsubscribeVisibleTimeRangeChange).toHaveBeenCalledWith(handlers[0])
    expect(timeScaleApis[1].unsubscribeVisibleTimeRangeChange).toHaveBeenCalledWith(handlers[1])
  })

  it('applies the selected range as the visible time window without dropping earlier data', async () => {
    render(
      <PortfolioChart
        historyRows={totalRows}
        compositionRows={totalRows}
        includeComposition
        displayCurrency="KRW"
        visibleRange={{ from: '2026-06-01', to: '2026-06-02' }}
      />,
    )

    await waitFor(() => {
      expect(timeScaleApis.some((api) => api.setVisibleRange.mock.calls.length > 0)).toBe(true)
    })
    expect(timeScaleApis.some((api) => (
      api.setVisibleRange.mock.calls.some(([range]) => (
        range.from === '2026-06-01' && range.to === '2026-06-02'
      ))
    ))).toBe(true)
    expect(timeScaleApis.some((api) => api.setVisibleLogicalRange.mock.calls.length > 0)).toBe(false)
  })
})
