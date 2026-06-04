import { buildChartSeries } from '@/components/dashboard/PortfolioChart'
import type { ScopedPortfolioHistory } from '@/lib/types'

const history: ScopedPortfolioHistory = {
  series: {
    KRW: [{
      snapshot_date: '2026-06-01',
      total_value: '750000',
      total_invested_principal: '600000',
      total_cost_basis: '700000',
      total_profit_loss: '150000',
      unavailable_price_count: 0,
      accounting_status: 'ok',
      warnings: [],
    }],
    USD: [{
      snapshot_date: '2026-06-01',
      total_value: '120',
      total_invested_principal: '80',
      total_cost_basis: '100',
      total_profit_loss: '40',
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

  it('maps value, invested principal, and profit for each currency', () => {
    const series = buildChartSeries(history.series)

    expect(series.KRW.cost).toEqual([{ time: '2026-06-01', value: 600000 }])
    expect(series.KRW.profit).toEqual([{ time: '2026-06-01', value: 150000 }])
  })

  it('omits unavailable values', () => {
    const series = buildChartSeries({
      KRW: [{ ...history.series.KRW[0], total_value: null }],
      USD: [],
    })

    expect(series.KRW.value).toEqual([])
  })
})
