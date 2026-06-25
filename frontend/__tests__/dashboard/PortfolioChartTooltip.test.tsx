import {
  toIsoDateKey,
  formatTooltipPercent,
  buildTooltipData,
} from '@/components/dashboard/PortfolioChart'
import type { DashboardHistoryRow } from '@/lib/types'

describe('toIsoDateKey', () => {
  it('returns ISO string inputs unchanged', () => {
    expect(toIsoDateKey('2026-06-25')).toBe('2026-06-25')
  })

  it('formats a BusinessDay object with zero padding', () => {
    expect(toIsoDateKey({ year: 2026, month: 6, day: 5 })).toBe('2026-06-05')
  })

  it('returns null for unsupported time shapes', () => {
    expect(toIsoDateKey(1750000000 as unknown)).toBeNull()
    expect(toIsoDateKey(undefined)).toBeNull()
    expect(toIsoDateKey(null)).toBeNull()
  })
})

describe('formatTooltipPercent', () => {
  it('formats with two decimals and percent sign', () => {
    expect(formatTooltipPercent(8.333)).toBe('8.33%')
  })

  it('keeps the minus sign for losses', () => {
    expect(formatTooltipPercent(-4.5)).toBe('-4.50%')
  })

  it('returns a dash for null', () => {
    expect(formatTooltipPercent(null)).toBe('-')
  })
})

const rows: DashboardHistoryRow[] = [
  {
    group_kind: 'total', group_id: null, group_name: '전체',
    snapshot_date: '2026-06-01',
    total_value: '750000', total_invested_principal: '600000',
    total_cost_basis: '700000', total_profit_loss: '50000',
  },
  {
    group_kind: 'total', group_id: null, group_name: '전체',
    snapshot_date: '2026-06-02',
    total_value: '760000', total_invested_principal: '600000',
    total_cost_basis: '700000', total_profit_loss: '60000',
  },
]

const dailyProfitChange = [
  { time: '2026-06-01' },
  { time: '2026-06-02', value: 10000, color: '#dc2626' },
]

describe('buildTooltipData', () => {
  it('builds per-date metrics keyed by ISO date with invested-principal base', () => {
    const map = buildTooltipData(rows, dailyProfitChange, 'invested')
    const day2 = map.get('2026-06-02')
    expect(day2).toEqual({
      date: '2026-06-02',
      value: 760000,
      profit: 60000,
      rate: 10, // 60000 / 600000 * 100
      daily: 10000,
      principal: 600000,
      principalLabel: '투자원금',
    })
  })

  it('uses cost basis and 잔여원금 label when referenceField is cost', () => {
    const map = buildTooltipData(rows, dailyProfitChange, 'cost')
    const day2 = map.get('2026-06-02')
    expect(day2?.principal).toBe(700000)
    expect(day2?.principalLabel).toBe('잔여원금')
    expect(day2?.rate).toBeCloseTo((60000 / 700000) * 100, 6)
  })

  it('returns null metrics when row fields are null', () => {
    const nullRows: DashboardHistoryRow[] = [{
      group_kind: 'total', group_id: null, group_name: '전체',
      snapshot_date: '2026-06-01',
      total_value: null, total_invested_principal: null,
      total_cost_basis: null, total_profit_loss: null,
    }]
    const map = buildTooltipData(nullRows, [{ time: '2026-06-01' }], 'invested')
    const day1 = map.get('2026-06-01')
    expect(day1).toEqual({
      date: '2026-06-01',
      value: null,
      profit: null,
      rate: null,
      daily: null,
      principal: null,
      principalLabel: '투자원금',
    })
  })

  it('returns null daily when the date is absent from dailyProfitChange', () => {
    const map = buildTooltipData(rows, [], 'invested')
    expect(map.get('2026-06-01')?.daily).toBeNull()
    expect(map.get('2026-06-02')?.daily).toBeNull()
  })

  it('returns null daily for whitespace dates and null rate when principal is 0', () => {
    const zeroRows: DashboardHistoryRow[] = [{
      group_kind: 'total', group_id: null, group_name: '전체',
      snapshot_date: '2026-06-01',
      total_value: '750000', total_invested_principal: '0',
      total_cost_basis: '700000', total_profit_loss: '50000',
    }]
    const map = buildTooltipData(zeroRows, [{ time: '2026-06-01' }], 'invested')
    const day1 = map.get('2026-06-01')
    expect(day1?.daily).toBeNull()
    expect(day1?.rate).toBeNull()
  })
})
