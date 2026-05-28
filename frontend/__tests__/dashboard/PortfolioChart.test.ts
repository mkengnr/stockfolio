import { buildChartData } from '@/components/dashboard/PortfolioChart'
import type { Snapshot } from '@/lib/types'

const makeSnapshots = (dates: string[], price: number): Snapshot[] =>
  dates.map((d) => ({
    snapshot_date: d,
    close_price: String(price),
    total_value: String(price * 10),
  }))

describe('buildChartData', () => {
  it('returns empty array for no holdings', () => {
    expect(buildChartData([])).toEqual([])
  })

  it('returns empty array for holdings with no snapshots', () => {
    expect(buildChartData([{ cost_basis: '100000', quantity: '10', snapshots: [] }])).toEqual([])
  })

  it('maps snapshots to date points', () => {
    const result = buildChartData([
      {
        cost_basis: '700000',
        quantity: '10',
        snapshots: makeSnapshots(['2024-01-10', '2024-01-11'], 75000),
      },
    ])
    expect(result).toHaveLength(2)
    expect(result[0]).toMatchObject({
      date: '2024-01-10',
      totalValue: 750000,
      totalCost: 700000,
    })
  })

  it('aggregates multiple holdings by date', () => {
    const result = buildChartData([
      {
        cost_basis: '700000',
        quantity: '10',
        snapshots: makeSnapshots(['2024-01-10'], 75000),
      },
      {
        cost_basis: '300000',
        quantity: '10',
        snapshots: makeSnapshots(['2024-01-10'], 32000),
      },
    ])
    expect(result).toHaveLength(1)
    expect(result[0].totalValue).toBe(750000 + 320000)
    expect(result[0].totalCost).toBe(700000 + 300000)
  })

  it('sorts result by date ascending', () => {
    const result = buildChartData([
      {
        cost_basis: '100000',
        quantity: '10',
        snapshots: makeSnapshots(['2024-01-15', '2024-01-10', '2024-01-12'], 10000),
      },
    ])
    expect(result[0].date).toBe('2024-01-10')
    expect(result[1].date).toBe('2024-01-12')
    expect(result[2].date).toBe('2024-01-15')
  })
})
