'use client'

import { cn, formatCurrency } from '@/lib/utils'
import type { Currency, DashboardExchangeRate, DisplayCurrency } from '@/lib/types'

interface Props {
  value: DisplayCurrency
  exchangeRate: DashboardExchangeRate | null
  onChange: (currency: DisplayCurrency) => void
}

export function DisplayCurrencyToggle({ value, exchangeRate, onChange }: Props) {
  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1 shadow-sm">
        <CurrencyButton label="KRW 환산" currency="KRW" value={value} onChange={onChange} />
        <CurrencyButton label="USD 별도" currency="USD" value={value} onChange={onChange} />
      </div>
      {exchangeRate && (
        <p className="text-xs text-gray-500">
          1 {exchangeRate.base} = {formatExchangeRate(exchangeRate)} · {formatExchangeRateDate(exchangeRate.as_of)} 기준
        </p>
      )}
    </div>
  )
}

function CurrencyButton({
  label,
  currency,
  value,
  onChange,
}: {
  label: string
  currency: DisplayCurrency
  value: DisplayCurrency
  onChange: (currency: DisplayCurrency) => void
}) {
  const active = currency === value
  return (
    <button
      type="button"
      className={cn(
        'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
        active ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
      )}
      aria-pressed={active}
      onClick={() => onChange(currency)}
    >
      {label}
    </button>
  )
}

function formatExchangeRate(exchangeRate: DashboardExchangeRate) {
  if (exchangeRate.quote === 'KRW' || exchangeRate.quote === 'USD') {
    return formatCurrency(exchangeRate.rate, exchangeRate.quote as Currency)
  }
  return `${exchangeRate.rate} ${exchangeRate.quote}`
}

function formatExchangeRateDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toISOString().slice(0, 10)
}
