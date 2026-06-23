import { formatDailyProfitBasis } from '@/components/dashboard/dailyProfitBasis'

describe('formatDailyProfitBasis', () => {
  it('uses price-date markets in KRX, US, then unknown-market order', () => {
    expect(formatDailyProfitBasis(
      { JP: '2026-06-20', US: '2026-06-22', KRX: '2026-06-23' },
      { US: '2026-06-18', KRX: '2026-06-20' },
      { KRX: false, US: true, JP: true },
    )).toBe('한국 당일 시세 없음 · 미국 2026-06-22 vs 2026-06-18 · JP 2026-06-20 기준')
  })

  it('shows a price-date market when the activity map is missing', () => {
    expect(formatDailyProfitBasis({ KRX: '2026-06-23' }, undefined, undefined))
      .toBe('한국 2026-06-23 기준')
  })

  it('ignores activity-only markets that have no price date', () => {
    expect(formatDailyProfitBasis(
      { US: '2026-06-22' },
      { US: '2026-06-18' },
      { US: true, KRX: false },
    )).toBe('미국 2026-06-22 vs 2026-06-18')
  })

  it('formats an active market without a comparison date', () => {
    expect(formatDailyProfitBasis({ US: '2026-06-22' }, {}, { US: true }))
      .toBe('미국 2026-06-22 기준')
  })

  it('returns an empty basis when price dates are absent', () => {
    expect(formatDailyProfitBasis(undefined, undefined, { US: true })).toBe('')
  })
})
