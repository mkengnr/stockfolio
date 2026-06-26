import { Card } from '@/components/ui/Card'
import { formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { Currency, HoldingPerformance } from '@/lib/types'

export function HoldingPerformanceSummary({
  performance, quantity, currency,
}: { performance: HoldingPerformance | null; quantity: string; currency: Currency }) {
  const cards = [
    { label: '보유수량', value: `${parseFloat(quantity).toLocaleString()}주` },
    { label: '투자원금', value: performance ? formatCurrency(performance.total_invested_principal, currency) : '—' },
    { label: '잔여원금', value: performance ? formatCurrency(performance.remaining_cost_basis, currency) : '—' },
    { label: '평가금액', value: performance?.current_value ? formatCurrency(performance.current_value, currency) : '—' },
    { label: '손익', value: performance?.profit_loss ? formatCurrency(performance.profit_loss, currency) : '—', colorClass: profitColor(performance?.profit_loss ?? null) },
    { label: '손익률', value: formatPercent(performance?.profit_loss_pct ?? null), colorClass: profitColor(performance?.profit_loss_pct ?? null) },
  ]
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {cards.map(({ label, value, colorClass }) => (
        <Card key={label}>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</p>
          <p className={`mt-1 text-lg font-bold tabular-nums ${colorClass ?? 'text-gray-900'}`}>{value}</p>
        </Card>
      ))}
    </div>
  )
}
