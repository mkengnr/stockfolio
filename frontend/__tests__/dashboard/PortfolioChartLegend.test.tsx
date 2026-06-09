import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { PortfolioChart } from '@/components/dashboard/PortfolioChart'
import type { DashboardHistoryRow } from '@/lib/types'

const timeScale = jest.fn(() => ({
  fitContent: jest.fn(),
  subscribeVisibleLogicalRangeChange: jest.fn(),
  setVisibleLogicalRange: jest.fn(),
}))
const createChart = jest.fn(() => ({
  addHistogramSeries: jest.fn(() => ({ setData: jest.fn() })),
  addLineSeries: jest.fn(() => ({ setData: jest.fn() })),
  timeScale,
  applyOptions: jest.fn(),
  remove: jest.fn(),
}))

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
  it('omits 일별손익 from the top legend while keeping the lower panel header', () => {
    render(
      <PortfolioChart
        historyRows={totalRows}
        compositionRows={totalRows}
        includeComposition
        displayCurrency="KRW"
      />,
    )

    expect(screen.getAllByText('일별손익')).toHaveLength(1)
    expect(screen.getByText('평가금액')).toBeInTheDocument()
    expect(screen.getByText('투자원금')).toBeInTheDocument()
  })
})
