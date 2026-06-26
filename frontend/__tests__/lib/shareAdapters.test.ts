import { toDashboardHolding, toDashboardHistoryRow } from '@/lib/shareAdapters'
import type { SharedDashboardHistoryRow, SharedDashboardHolding } from '@/lib/types'

const sharedHolding: SharedDashboardHolding = {
  holding_id: 'holding-1',
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
}

describe('toDashboardHolding', () => {
  it('passes the holding id through so shared rows can link to the detail page', () => {
    const row = toDashboardHolding(sharedHolding)

    expect(row.holding_id).toBe('holding-1')
    expect(row.ticker).toBe('AAPL')
    expect(row.current_value_change).toBe('10')
    expect(row.groups).toEqual([
      { name: '급여', color: '#4f46e5', remaining_quantity: '2', source_group_id: null },
    ])
  })
})

describe('toDashboardHistoryRow', () => {
  const base: SharedDashboardHistoryRow = {
    group_key: 'group-1',
    group_kind: 'source',
    group_name: '급여',
    snapshot_date: '2026-06-01',
    total_value: '240',
    total_invested_principal: '200',
    total_cost_basis: '200',
    total_profit_loss: '40',
  }

  it('uses the opaque group key as the row id', () => {
    expect(toDashboardHistoryRow(base).group_id).toBe('group-1')
  })

  it('maps the total row to a null group id', () => {
    expect(
      toDashboardHistoryRow({ ...base, group_key: 'total', group_kind: 'total', group_name: '전체' }).group_id,
    ).toBeNull()
  })
})
