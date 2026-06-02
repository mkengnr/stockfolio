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

  const groups = (['KRW', 'USD'] as const)
    .map((currency) => ({ currency, holdings: active.filter((h) => h.currency === currency) }))
    .filter(({ holdings: currencyHoldings }) => currencyHoldings.length > 0)

  if (groups.length === 0) {
    return <CurrencySummary currency="KRW" holdings={[]} />
  }

  return (
    <div className="flex flex-col gap-4">
      {groups.map(({ currency, holdings: currencyHoldings }) => (
        <div key={currency}>
          {groups.length > 1 && <p className="mb-2 text-xs font-semibold text-gray-400">{currency}</p>}
          <CurrencySummary currency={currency} holdings={currencyHoldings} />
        </div>
      ))}
    </div>
  )
}

function CurrencySummary({ currency, holdings }: { currency: 'KRW' | 'USD'; holdings: Holding[] }) {
  const totalCost = holdings.reduce((s, h) => s + parseFloat(h.cost_basis ?? '0'), 0)
  const totalValue = holdings.reduce((s, h) => {
    const v = h.current_value ? parseFloat(h.current_value) : parseFloat(h.cost_basis ?? '0')
    return s + v
  }, 0)
  const totalPL = totalValue - totalCost
  const totalPLPct = totalCost > 0 ? (totalPL / totalCost) * 100 : 0
  const hasPrices = holdings.length > 0 && holdings.every((h) => h.current_price !== null)

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
