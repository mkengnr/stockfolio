import { buildDashboardChartSeries } from '@/components/dashboard/PortfolioChart'
import type { DashboardHistoryRow } from '@/lib/types'

const rows: DashboardHistoryRow[] = [
  {
    group_kind: 'combined',
    group_id: 'combined-1',
    group_name: '가족',
    snapshot_date: '2026-06-01',
    total_value: '500000',
    total_invested_principal: '450000',
    total_cost_basis: '460000',
    total_profit_loss: '40000',
  },
  {
    group_kind: 'total',
    group_id: null,
    group_name: '전체',
    snapshot_date: '2026-06-01',
    total_value: '750000',
    total_invested_principal: '600000',
    total_cost_basis: '700000',
    total_profit_loss: '150000',
  },
  {
    group_kind: 'source',
    group_id: 'source-1',
    group_name: '모음통장',
    snapshot_date: '2026-06-01',
    total_value: '300000',
    total_invested_principal: '250000',
    total_cost_basis: '260000',
    total_profit_loss: '40000',
  },
]

describe('buildDashboardChartSeries', () => {
  it('builds stable value series with total first', () => {
    const series = buildDashboardChartSeries(rows, { metric: 'value' })

    expect(series).toEqual([
      {
        id: 'total:total',
        name: '전체',
        kind: 'total',
        points: [{ time: '2026-06-01', value: 750000 }],
      },
      {
        id: 'source:source-1',
        name: '모음통장',
        kind: 'source',
        points: [{ time: '2026-06-01', value: 300000 }],
      },
      {
        id: 'combined:combined-1',
        name: '가족',
        kind: 'combined',
        points: [{ time: '2026-06-01', value: 500000 }],
      },
    ])
  })

  it('builds grouped rows in the selected metric', () => {
    const series = buildDashboardChartSeries(rows, { metric: 'principal' })

    expect(series[0]).toEqual({
      id: 'total:total',
      name: '전체',
      kind: 'total',
      points: [{ time: '2026-06-01', value: 600000 }],
    })
    expect(series[1]).toEqual(
      {
        id: 'source:source-1',
        name: '모음통장',
        kind: 'source',
        points: [{ time: '2026-06-01', value: 250000 }],
      },
    )
  })

  it('omits unavailable values', () => {
    const series = buildDashboardChartSeries([{ ...rows[0], total_value: null }], {
      metric: 'value',
    })

    expect(series[0].points).toEqual([])
  })
})
