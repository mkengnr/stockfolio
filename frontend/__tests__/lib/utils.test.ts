import '@testing-library/jest-dom'
import {
  formatCurrency,
  formatPercent,
  formatNumber,
  profitColor,
  detectMarket,
  formatDate,
  today,
} from '@/lib/utils'

describe('formatCurrency', () => {
  it('formats KRW without decimals', () => {
    expect(formatCurrency(75000, 'KRW')).toMatch(/75,000/)
    expect(formatCurrency(75000, 'KRW')).toMatch(/₩/)
  })

  it('formats USD with two decimals', () => {
    expect(formatCurrency(185.5, 'USD')).toBe('$185.50')
  })

  it('formats USD whole number with .00', () => {
    expect(formatCurrency(200, 'USD')).toBe('$200.00')
  })

  it('returns — for NaN string input', () => {
    expect(formatCurrency('abc', 'KRW')).toBe('—')
  })

  it('handles string number input', () => {
    expect(formatCurrency('75000', 'KRW')).toMatch(/75,000/)
  })
})

describe('formatPercent', () => {
  it('shows + sign for positive', () => {
    expect(formatPercent(12.34)).toBe('+12.34%')
  })

  it('shows – sign for negative', () => {
    expect(formatPercent(-5.67)).toBe('-5.67%')
  })

  it('shows +0.00% for zero', () => {
    expect(formatPercent(0)).toBe('+0.00%')
  })

  it('returns — for null', () => {
    expect(formatPercent(null)).toBe('—')
  })

  it('parses string input', () => {
    expect(formatPercent('8.50')).toBe('+8.50%')
  })

  it('returns — for undefined', () => {
    expect(formatPercent(undefined as unknown as null)).toBe('—')
  })
})

describe('formatNumber', () => {
  it('formats integer without decimals by default', () => {
    expect(formatNumber(1000000)).toContain('1,000,000')
  })

  it('respects decimals param', () => {
    expect(formatNumber(1.5, 2)).toContain('1.5')
  })

  it('returns — for NaN', () => {
    expect(formatNumber(NaN)).toBe('—')
  })
})

describe('profitColor', () => {
  it('returns green for positive', () => {
    expect(profitColor(10)).toBe('text-green-600')
  })

  it('returns red for negative', () => {
    expect(profitColor(-5)).toBe('text-red-500')
  })

  it('returns gray for zero', () => {
    expect(profitColor(0)).toBe('text-gray-500')
  })

  it('returns gray for null', () => {
    expect(profitColor(null)).toBe('text-gray-500')
  })

  it('parses string input', () => {
    expect(profitColor('3.5')).toBe('text-green-600')
    expect(profitColor('-1.2')).toBe('text-red-500')
  })
})

describe('detectMarket', () => {
  it('detects KRX for 6-digit numeric', () => {
    expect(detectMarket('005930')).toBe('KRX')
    expect(detectMarket('000660')).toBe('KRX')
  })

  it('detects US for alphabetic tickers', () => {
    expect(detectMarket('AAPL')).toBe('US')
    expect(detectMarket('TSLA')).toBe('US')
  })

  it('detects US for 5-digit numeric', () => {
    expect(detectMarket('12345')).toBe('US')
  })

  it('detects US for 7-digit numeric', () => {
    expect(detectMarket('0059300')).toBe('US')
  })

  it('detects US for mixed alphanumeric', () => {
    expect(detectMarket('BRK.B')).toBe('US')
  })

  it('trims whitespace before detecting', () => {
    expect(detectMarket(' 005930 ')).toBe('KRX')
    expect(detectMarket(' AAPL ')).toBe('US')
  })
})

describe('today', () => {
  it('returns a string in YYYY-MM-DD format', () => {
    expect(today()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('matches the current date', () => {
    const d = new Date().toISOString().slice(0, 10)
    expect(today()).toBe(d)
  })
})
