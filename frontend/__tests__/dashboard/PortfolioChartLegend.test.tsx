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
  unsubscribeVisibleLogicalRangeChange: jest.Mock
  setVisibleLogicalRange: jest.Mock
}> = []
const histogramSeriesApis: Array<{ setData: jest.Mock }> = []
const lineSeriesApis: Array<{ setData: jest.Mock }> = []
const createChart = jest.fn(() => {
  const timeScaleApi = {
      fitContent: jest.fn(),
      setVisibleRange: jest.fn(),
      subscribeVisibleTimeRangeChange: jest.fn(),
      unsubscribeVisibleTimeRangeChange: jest.fn(),
      subscribeVisibleLogicalRangeChange: jest.fn(),
      unsubscribeVisibleLogicalRangeChange: jest.fn(),
      setVisibleLogicalRange: jest.fn(),
  }
  timeScaleApis.push(timeScaleApi)
  return {
    addHistogramSeries: jest.fn(() => {
      const series = { setData: jest.fn() }
      histogramSeriesApis.push(series)
      return series
    }),
    addLineSeries: jest.fn(() => {
      const series = { setData: jest.fn(), attachPrimitive: jest.fn() }
      lineSeriesApis.push(series)
      return series
    }),
    timeScale: jest.fn(() => timeScaleApi),
    subscribeCrosshairMove: jest.fn(),
    unsubscribeCrosshairMove: jest.fn(),
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
    lineSeriesApis.length = 0
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

  it('gives the main chart a whitespace date spine matching the profit chart so logical indices align', async () => {
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

    // Both charts must carry the same dates: the profit histogram spans every date as data or
    // whitespace, and the main chart must receive an equivalent whitespace spine so their logical
    // bar indices line up 1:1 for exact pan/zoom synchronization.
    await waitFor(() => {
      expect(lineSeriesApis.length).toBeGreaterThan(0)
    })
    const spine = [{ time: '2026-06-01' }, { time: '2026-06-02' }]
    expect(lineSeriesApis.some((series) => (
      series.setData.mock.calls.some(([data]) => JSON.stringify(data) === JSON.stringify(spine))
    ))).toBe(true)
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

  it('shows the upper time scale and synchronizes the charts by logical range with cleanup', async () => {
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
      expect(timeScaleApis.every((api) => api.subscribeVisibleLogicalRangeChange.mock.calls.length === 1)).toBe(true)
    })

    expect(createChart.mock.calls[0][1].timeScale.visible).toBe(true)
    expect(createChart.mock.calls[0][1].timeScale.rightOffset).toBe(
      createChart.mock.calls[1][1].timeScale.rightOffset,
    )
    expect(createChart.mock.calls[0][1].leftPriceScale.minimumWidth).toBe(96)
    expect(createChart.mock.calls[1][1].leftPriceScale.minimumWidth).toBe(96)
    // Synchronization is by logical bar index (pixel-exact), not by approximate time range.
    expect(timeScaleApis.every((api) => api.subscribeVisibleTimeRangeChange.mock.calls.length === 0)).toBe(true)

    const handlers = timeScaleApis.map(
      (api) => api.subscribeVisibleLogicalRangeChange.mock.calls[0][0],
    )
    const range = { from: 0.5, to: 1.5 }
    handlers[0](range)
    expect(timeScaleApis[1].setVisibleLogicalRange).toHaveBeenCalledWith(range)

    // The echoed range must not bounce back to the source chart.
    handlers[1](range)
    expect(timeScaleApis[0].setVisibleLogicalRange).not.toHaveBeenCalled()

    const nextRange = { from: 1, to: 2 }
    handlers[1](nextRange)
    expect(timeScaleApis[0].setVisibleLogicalRange).toHaveBeenCalledTimes(1)
    expect(timeScaleApis[0].setVisibleLogicalRange).toHaveBeenCalledWith(nextRange)

    handlers[0](nextRange)
    expect(timeScaleApis[1].setVisibleLogicalRange).toHaveBeenCalledTimes(1)

    unmount()

    expect(timeScaleApis[0].unsubscribeVisibleLogicalRangeChange).toHaveBeenCalledWith(handlers[0])
    expect(timeScaleApis[1].unsubscribeVisibleLogicalRangeChange).toHaveBeenCalledWith(handlers[1])
  })

  it('configures ISO date labels and a crosshair subscription with cleanup', async () => {
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
    })
    expect(createChart.mock.calls[0][1].localization.dateFormat).toBe('yyyy-MM-dd')

    const mainChart = createChart.mock.results[0].value
    await waitFor(() => {
      expect(mainChart.subscribeCrosshairMove).toHaveBeenCalledTimes(1)
    })
    const handler = mainChart.subscribeCrosshairMove.mock.calls[0][0]

    unmount()
    expect(mainChart.unsubscribeCrosshairMove).toHaveBeenCalledWith(handler)
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
