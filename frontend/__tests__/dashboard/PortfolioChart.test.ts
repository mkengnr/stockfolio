import { createElement } from 'react'
import { render, screen } from '@testing-library/react'
import {
  PortfolioChart,
  buildDashboardChartSeries,
  buildIntegratedDashboardChartData,
  formatDashboardMoney,
  getDashboardChartLayout,
  hasInvestedPrincipal,
  mergeDashboardCompositionLivePoints,
  mergeDashboardLivePoint,
} from '@/components/dashboard/PortfolioChart'
import type { DashboardHistoryRow, DashboardSummary } from '@/lib/types'

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

const liveSummary: DashboardSummary = {
  total_invested_principal: '600000',
  total_cost_basis: '700000',
  total_current_value: '805000',
  total_current_value_change: '-25000',
  total_current_value_change_pct: '-3.01',
  total_unrealized_profit_loss: '90000',
  total_unrealized_profit_loss_pct: '12.86',
  total_profit_loss: '180000',
  total_profit_loss_pct: '30',
}

describe('mergeDashboardLivePoint', () => {
  const totalRows = rows.filter((row) => row.group_kind === 'total')

  it('appends a live total point in date order and exposes its daily profit', () => {
    const originalRows = totalRows.map((row) => ({ ...row }))

    const result = mergeDashboardLivePoint(totalRows, {
      snapshotDate: '2026-06-03',
      groupKind: 'total',
      groupId: null,
      groupName: '전체',
      summary: liveSummary,
    })

    expect(result.rows).toEqual([
      ...originalRows,
      {
        group_kind: 'total',
        group_id: null,
        group_name: '전체',
        snapshot_date: '2026-06-03',
        total_value: '805000',
        total_invested_principal: '600000',
        total_cost_basis: '700000',
        total_profit_loss: '180000',
      },
    ])
    expect(result.liveDailyProfit).toBe(-25000)
    expect(totalRows).toEqual(originalRows)
  })

  it('ignores a live point dated before the latest confirmed snapshot', () => {
    const result = mergeDashboardLivePoint(totalRows, {
      snapshotDate: '2026-06-01',
      groupKind: 'total',
      groupId: null,
      groupName: '전체',
      summary: liveSummary,
    })

    expect(result.rows).toBe(totalRows)
    expect(result.liveDailyProfit).toBeUndefined()
    expect(result.liveDailyProfitDate).toBeUndefined()
  })

  it('leaves sibling groups intact when a stale same-date live point is ignored', () => {
    const sourceRow = rows.find(
      (row) => row.group_kind === 'source' && row.snapshot_date === '2026-06-02',
    )!
    const mixedRows = [...totalRows, sourceRow]

    const result = mergeDashboardLivePoint(mixedRows, {
      snapshotDate: '2026-06-02',
      groupKind: 'total',
      groupId: null,
      groupName: '전체',
      summary: liveSummary,
    })

    expect(result.rows).toBe(mixedRows)
    expect(result.rows.filter((row) => row.snapshot_date === '2026-06-02')).toEqual([
      expect.objectContaining({ group_kind: 'total', total_value: '780000' }),
      sourceRow,
    ])
  })

  it.each([
    ['null', null],
    ['undefined', undefined],
  ])('returns the original rows for a %s live point', (_label, livePoint) => {
    const result = mergeDashboardLivePoint(totalRows, livePoint)

    expect(result.rows).toBe(totalRows)
    expect(result.liveDailyProfit).toBeUndefined()
  })

  it.each([
    ['a missing live date', null, liveSummary],
    ['a missing live value', '2026-06-03', { ...liveSummary, total_current_value: null }],
  ])('returns the original rows for %s', (_label, snapshotDate, summary) => {
    const result = mergeDashboardLivePoint(totalRows, {
      snapshotDate,
      groupKind: 'total',
      groupId: null,
      groupName: '전체',
      summary,
    })

    expect(result.rows).toBe(totalRows)
    expect(result.liveDailyProfit).toBeUndefined()
  })

  it('preserves the final confirmed delta when an invalid merge result is composed into chart data', () => {
    const merged = mergeDashboardLivePoint(totalRows, null)

    const data = buildIntegratedDashboardChartData(rows, merged.rows, {
      includeComposition: false,
      liveDailyProfit: merged.liveDailyProfit,
      liveDailyProfitDate: merged.liveDailyProfitDate,
    })

    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-01' },
      { time: '2026-06-02', value: 15000, color: '#dc2626' },
    ])
  })

  it('uses final whitespace when a valid live merge has no daily profit', () => {
    const merged = mergeDashboardLivePoint(totalRows, {
      snapshotDate: '2026-06-03',
      groupKind: 'total',
      groupId: null,
      groupName: '전체',
      summary: { ...liveSummary, total_current_value_change: null },
    })

    const data = buildIntegratedDashboardChartData(rows, merged.rows, {
      includeComposition: false,
      liveDailyProfit: merged.liveDailyProfit,
      liveDailyProfitDate: merged.liveDailyProfitDate,
    })

    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-01' },
      { time: '2026-06-02', value: 15000, color: '#dc2626' },
      { time: '2026-06-03' },
    ])
  })

  it('keeps the confirmed close-to-close profit when the live point only restates the latest closed day', () => {
    // Pre-open scenario: the latest price date is still the last confirmed close (e.g. KRX before
    // 09:00), so the live point's date collides with that confirmed snapshot and its 당일손익 is a
    // stale 0. The confirmed close-to-close change must win, not be overwritten by the live 0.
    const merged = mergeDashboardLivePoint(totalRows, {
      snapshotDate: '2026-06-02',
      groupKind: 'total',
      groupId: null,
      groupName: '전체',
      summary: { ...liveSummary, total_current_value_change: '0' },
    })

    expect(merged.rows).toBe(totalRows)
    expect(merged.liveDailyProfit).toBeUndefined()
    expect(merged.liveDailyProfitDate).toBeUndefined()

    const data = buildIntegratedDashboardChartData(totalRows, merged.rows, {
      includeComposition: false,
      liveDailyProfit: merged.liveDailyProfit,
      liveDailyProfitDate: merged.liveDailyProfitDate,
    })

    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-01' },
      { time: '2026-06-02', value: 15000, color: '#dc2626' },
    ])
  })

  it('retains the selected group identity when the live point has no history', () => {
    const result = mergeDashboardLivePoint([], {
      snapshotDate: '2026-06-03',
      groupKind: 'combined',
      groupId: 'combined-7',
      groupName: '장기 투자',
      summary: liveSummary,
    })

    expect(result.rows).toEqual([
      expect.objectContaining({
        group_kind: 'combined',
        group_id: 'combined-7',
        group_name: '장기 투자',
      }),
    ])
  })
})

describe('mergeDashboardCompositionLivePoints', () => {
  it('replaces multiple identities with one batch sort and preserves inputs and sibling groups', () => {
    const inputRows = rows.map((row) => ({ ...row }))
    const livePoints = [
      {
        snapshotDate: '2026-06-02',
        groupKind: 'source' as const,
        groupId: 'source-1',
        groupName: '모음통장',
        summary: liveSummary,
      },
      {
        snapshotDate: '2026-06-02',
        groupKind: 'unclassified' as const,
        groupId: null,
        groupName: '미분류',
        summary: { ...liveSummary, total_current_value: '70000' },
      },
    ]
    const originalLivePoints = livePoints.map((point) => ({ ...point, summary: { ...point.summary } }))
    const sortSpy = jest.spyOn(Array.prototype, 'sort')

    const result = mergeDashboardCompositionLivePoints(inputRows, livePoints)
    const sortCallCount = sortSpy.mock.calls.length
    sortSpy.mockRestore()

    expect(sortCallCount).toBe(1)
    expect(result.filter((row) => row.snapshot_date === '2026-06-02')).toEqual(expect.arrayContaining([
      expect.objectContaining({ group_kind: 'total', total_value: '780000' }),
      expect.objectContaining({ group_kind: 'source', group_id: 'source-1', total_value: '805000' }),
      expect.objectContaining({ group_kind: 'unclassified', group_id: null, total_value: '70000' }),
    ]))
    expect(inputRows).toEqual(rows)
    expect(livePoints).toEqual(originalLivePoints)
  })

  it('ignores live composition points with missing dates or values', () => {
    const result = mergeDashboardCompositionLivePoints(rows, [
      {
        snapshotDate: null,
        groupKind: 'source',
        groupId: 'source-1',
        groupName: '모음통장',
        summary: liveSummary,
      },
      {
        snapshotDate: '2026-06-02',
        groupKind: 'unclassified',
        groupId: null,
        groupName: '미분류',
        summary: { ...liveSummary, total_current_value: null },
      },
      {
        snapshotDate: 'not-a-date',
        groupKind: 'source',
        groupId: 'source-1',
        groupName: '모음통장',
        summary: liveSummary,
      },
      {
        snapshotDate: '2026-06-02',
        groupKind: 'unclassified',
        groupId: null,
        groupName: '미분류',
        summary: { ...liveSummary, total_current_value: 'not-a-number' },
      },
    ])

    expect(result).toBe(rows)
  })

  it('does not inspect live composition when composition display is disabled', () => {
    const unusedLiveComposition = new Proxy([], {
      get(_target, property) {
        if (property === Symbol.iterator) throw new Error('composition merge should be skipped')
        return Reflect.get(_target, property)
      },
    })

    render(createElement(PortfolioChart, {
      historyRows: [],
      compositionRows: [],
      includeComposition: false,
      displayCurrency: 'KRW',
      visibleRange: null,
      liveComposition: unusedLiveComposition,
    }))

    expect(screen.getByText('차트 데이터가 없습니다.')).not.toBeNull()
  })
})

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
      points: [{ time: '2026-06-01', value: 700000 }],
    })
    expect(series[1]).toEqual(
      {
        id: 'source:source-1',
        name: '모음통장',
        kind: 'source',
        points: [{ time: '2026-06-01', value: 260000 }],
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
      { time: '2026-06-01', value: 700000 },
      { time: '2026-06-02', value: 700000 },
    ])
    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-01' },
      { time: '2026-06-02', value: 15000, color: '#dc2626' },
    ])
    expect(data.gainLossBand).toEqual([
      { time: '2026-06-01', value: 750000, principal: 700000 },
      { time: '2026-06-02', value: 780000, principal: 700000 },
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

  it('builds the principal line and gain/loss band from 투자원금 when referenceField is invested', () => {
    const selectedRows = rows.filter((row) => row.group_kind === 'total')

    const data = buildIntegratedDashboardChartData(rows, selectedRows, {
      includeComposition: false,
      referenceField: 'invested',
    })

    expect(data.principal).toEqual([
      { time: '2026-06-01', value: 600000 },
      { time: '2026-06-02', value: 600000 },
    ])
    expect(data.gainLossBand).toEqual([
      { time: '2026-06-01', value: 750000, principal: 600000 },
      { time: '2026-06-02', value: 780000, principal: 600000 },
    ])
  })

  it('uses the exact negative live daily profit for the final row', () => {
    const selectedRows = [
      ...rows.filter((row) => row.group_kind === 'total'),
      {
        ...rows.find((row) => row.group_kind === 'total' && row.snapshot_date === '2026-06-02')!,
        snapshot_date: '2026-06-03',
        total_value: '805000',
        total_profit_loss: '180000',
      },
    ]

    const data = buildIntegratedDashboardChartData(rows, selectedRows, {
      includeComposition: false,
      liveDailyProfit: -25000,
      liveDailyProfitDate: '2026-06-03',
    })

    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-01' },
      { time: '2026-06-02', value: 15000, color: '#dc2626' },
      { time: '2026-06-03', value: -25000, color: '#2563eb' },
    ])
  })

  it('uses whitespace for the final live row when live daily profit is explicitly null', () => {
    const selectedRows = [
      ...rows.filter((row) => row.group_kind === 'total'),
      {
        ...rows.find((row) => row.group_kind === 'total' && row.snapshot_date === '2026-06-02')!,
        snapshot_date: '2026-06-03',
        total_value: '805000',
        total_profit_loss: '180000',
      },
    ]

    const data = buildIntegratedDashboardChartData(rows, selectedRows, {
      includeComposition: false,
      liveDailyProfit: null,
      liveDailyProfitDate: '2026-06-03',
    })

    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-01' },
      { time: '2026-06-02', value: 15000, color: '#dc2626' },
      { time: '2026-06-03' },
    ])
  })

  it('keeps missing profit dates aligned and resumes changes from the next confirmed profit', () => {
    const selectedRows = [
      ...rows.filter((row) => row.group_kind === 'total'),
      {
        ...rows.find((row) => row.group_kind === 'total' && row.snapshot_date === '2026-06-02')!,
        snapshot_date: '2026-06-03',
        total_profit_loss: null,
      },
      {
        ...rows.find((row) => row.group_kind === 'total' && row.snapshot_date === '2026-06-02')!,
        snapshot_date: '2026-06-04',
        total_profit_loss: '180000',
      },
      {
        ...rows.find((row) => row.group_kind === 'total' && row.snapshot_date === '2026-06-02')!,
        snapshot_date: '2026-06-05',
        total_profit_loss: '175000',
      },
    ]

    const data = buildIntegratedDashboardChartData(rows, selectedRows, {
      includeComposition: false,
    })

    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-01' },
      { time: '2026-06-02', value: 15000, color: '#dc2626' },
      { time: '2026-06-03' },
      { time: '2026-06-04' },
      { time: '2026-06-05', value: -5000, color: '#2563eb' },
    ])
  })

  it('applies live daily profit to its own date when a newer confirmed row exists', () => {
    const selectedRows = [
      ...rows.filter((row) => row.group_kind === 'total'),
      {
        ...rows.find((row) => row.group_kind === 'total' && row.snapshot_date === '2026-06-02')!,
        snapshot_date: '2026-06-03',
        total_profit_loss: '190000',
      },
    ]

    const data = buildIntegratedDashboardChartData(rows, selectedRows, {
      includeComposition: false,
      liveDailyProfit: -25000,
      liveDailyProfitDate: '2026-06-02',
    })

    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-01' },
      { time: '2026-06-02', value: -25000, color: '#2563eb' },
      { time: '2026-06-03', value: 25000, color: '#dc2626' },
    ])
  })

  it('detects whether 투자원금 is available for the auto default', () => {
    const withPrincipal = rows.filter((row) => row.group_kind === 'total')
    expect(hasInvestedPrincipal(withPrincipal)).toBe(true)

    const zeroed = withPrincipal.map((row) => ({ ...row, total_invested_principal: '0' }))
    expect(hasInvestedPrincipal(zeroed)).toBe(false)

    const missing = withPrincipal.map((row) => ({ ...row, total_invested_principal: null }))
    expect(hasInvestedPrincipal(missing)).toBe(false)
  })

  it('excludes composition for a selected group and formats rounded money', () => {
    const selectedRows = rows.filter((row) => row.group_kind === 'source')

    const data = buildIntegratedDashboardChartData(rows, selectedRows, { includeComposition: false })

    expect(data.composition).toEqual([])
    expect(data.dailyProfitChange).toEqual([
      { time: '2026-06-01' },
      { time: '2026-06-02', value: 15000, color: '#dc2626' },
    ])
    expect(formatDashboardMoney(1234567.89)).toBe('1,234,568')
  })
})

describe('getDashboardChartLayout', () => {
  it('renders daily profit in a distinct lower chart panel', () => {
    expect(getDashboardChartLayout()).toEqual({
      mainHeight: 320,
      profitHeight: 110,
    })
  })
})
