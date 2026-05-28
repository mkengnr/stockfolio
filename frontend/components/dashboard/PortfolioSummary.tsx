import { Card, CardTitle } from '@/components/ui/Card'
import { cn, formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { Holding } from '@/lib/types'

interface SummaryCardProps {
  title: string
  value: string
  sub?: string
  subColor?: string
}

function SummaryCard({ title, value, sub, subColor }: SummaryCardProps) {
  return (
    <Card>
      <CardTitle>{title}</CardTitle>
      <p className="mt-2 text-2xl font-bold text-gray-900 tabular-nums">{value}</p>
      {sub && <p className={cn('mt-1 text-sm font-medium', subColor ?? 'text-gray-500')}>{sub}</p>}
    </Card>
  )
}

interface Props {
  holdings: Holding[]
}

export function PortfolioSummary({ holdings }: Props) {
  const active = holdings.filter((h) => h.is_active)

  const totalCost = active.reduce((s, h) => s + parseFloat(h.cost_basis ?? '0'), 0)
  const totalValue = active.reduce((s, h) => {
    const v = h.current_value ? parseFloat(h.current_value) : parseFloat(h.cost_basis ?? '0')
    return s + v
  }, 0)
  const totalPL = totalValue - totalCost
  const totalPLPct = totalCost > 0 ? (totalPL / totalCost) * 100 : 0
  const hasPrices = active.some((h) => h.current_price !== null)

  // KRW dominant: use KRW if more than half of holdings are KRW
  const krwCount = active.filter((h) => h.currency === 'KRW').length
  const currency = krwCount >= active.length / 2 ? 'KRW' : 'USD'

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <SummaryCard title="총 투자원금" value={formatCurrency(totalCost, currency)} />
      <SummaryCard
        title="총 평가금액"
        value={hasPrices ? formatCurrency(totalValue, currency) : '—'}
        sub={hasPrices ? undefined : '시세 로딩 중'}
      />
      <SummaryCard
        title="평가손익"
        value={hasPrices ? formatCurrency(totalPL, currency) : '—'}
        subColor={profitColor(totalPL)}
      />
      <SummaryCard
        title="수익률"
        value={hasPrices ? formatPercent(totalPLPct) : '—'}
        subColor={profitColor(totalPLPct)}
      />
    </div>
  )
}
