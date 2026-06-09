import {
  buildDashboardChartSeries,
  buildIntegratedDashboardChartData,
  formatDashboardMoney,
} from '@/components/dashboard/PortfolioChart'
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
  {
    group_kind: 'unclassified',
    group_id: null,
    group_name: '미분류',
    snapshot_date: '2026-06-01',
    total_value: '50000',
    total_invested_principal: '40000',
    total_cost_basis: '45000',
    total_profit_loss: '5000',
  },
  {
    group_kind: 'total',
    group_id: null,
    group_name: '전체',
    snapshot_date: '2026-06-02',
    total_value: '780000',
    total_invested_principal: '600000',
    total_cost_basis: '700000',
    total_profit_loss: '165000',
  },
  {
    group_kind: 'source',
    group_id: 'source-1',
    group_name: '모음통장',
    snapshot_date: '2026-06-02',
    total_value: '320000',
    total_invested_principal: '250000',
    total_cost_basis: '260000',
    total_profit_loss: '55000',
  },
  {
    group_kind: 'unclassified',
    group_id: null,
    group_name: '미분류',
    snapshot_date: '2026-06-02',
    total_value: '60000',
    total_invested_principal: '40000',
    total_cost_basis: '45000',
    total_profit_loss: '15000',
  },
]

describe('buildDashboardChartSeries', () => {
  it('builds stable value series with total first', () => {
    const series = buildDashboardChartSeries(rows.slice(0, 3), { metric: 'value' })

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
    const series = buildDashboardChartSeries(rows.slice(0, 3), { metric: 'principal' })

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

describe('buildIntegratedDashboardChartData', () => {
  it('builds selected value, principal, daily profit change, and non-overlapping cumulative composition', () => {
    const selectedRows = rows.filter((row) => row.group_kind === 'total')

    const data = buildIntegratedDashboardChartData(rows, selectedRows, { includeComposition: true })

    expect(data.value).toEqual([
      { time: '2026-06-01', value: 750000 },
      { time: '2026-06-02', value: 780000 },
    ])
    expect(data.principal).toEqual([
      { time: '2026-06-01', value: 600000 },
      { time: '2026-06-02', value: 600000 },
    ])
    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-02', value: 15000, color: '#16a34a' },
    ])
    expect(data.composition.map((series) => series.kind)).toEqual(['source', 'unclassified'])
    expect(data.composition[0].points).toEqual([
      { time: '2026-06-01', value: 300000 },
      { time: '2026-06-02', value: 320000 },
    ])
    expect(data.composition[1].points).toEqual([
      { time: '2026-06-01', value: 350000 },
      { time: '2026-06-02', value: 380000 },
    ])
  })

  it('excludes composition for a selected group and formats rounded money', () => {
    const selectedRows = rows.filter((row) => row.group_kind === 'source')

    const data = buildIntegratedDashboardChartData(rows, selectedRows, { includeComposition: false })

    expect(data.composition).toEqual([])
    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-02', value: 15000, color: '#16a34a' },
    ])
    expect(formatDashboardMoney(1234567.89)).toBe('1,234,568')
  })
})
