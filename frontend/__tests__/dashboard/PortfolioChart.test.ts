import { buildChartSeries } from '@/components/dashboard/PortfolioChart'
import type { ScopedPortfolioHistory } from '@/lib/types'

const history: ScopedPortfolioHistory = {
  series: {
    KRW: [{
      snapshot_date: '2026-06-01',
      total_value: '750000',
      total_cost_basis: '700000',
      total_profit_loss: '50000',
      unavailable_price_count: 0,
      accounting_status: 'ok',
      warnings: [],
    }],
    USD: [{
      snapshot_date: '2026-06-01',
      total_value: '120',
      total_cost_basis: '100',
      total_profit_loss: '20',
      unavailable_price_count: 0,
      accounting_status: 'ok',
      warnings: [],
    }],
  },
}

describe('buildChartSeries', () => {
  it('keeps KRW and USD series separate instead of adding currencies', () => {
    const series = buildChartSeries(history.series)

    expect(series.KRW.value).toEqual([{ time: '2026-06-01', value: 750000 }])
    expect(series.USD.value).toEqual([{ time: '2026-06-01', value: 120 }])
  })

  it('maps value, remaining cost, and profit for each currency', () => {
    const series = buildChartSeries(history.series)

    expect(series.KRW.cost).toEqual([{ time: '2026-06-01', value: 700000 }])
    expect(series.KRW.profit).toEqual([{ time: '2026-06-01', value: 50000 }])
  })

  it('omits unavailable values', () => {
    const series = buildChartSeries({
      KRW: [{ ...history.series.KRW[0], total_value: null }],
      USD: [],
    })

    expect(series.KRW.value).toEqual([])
  })
})
