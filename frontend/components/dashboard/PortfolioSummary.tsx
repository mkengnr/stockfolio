import { Card, CardTitle } from '@/components/ui/Card'
import { cn, formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type {
  Currency, DashboardSummary, DisplayCurrency, Holding, PortfolioCurrencySummary,
  PortfolioSummary as SummaryPayload,
} from '@/lib/types'

interface SummaryCardProps {
  title: string
  value: string
  sub?: string
  subColor?: string
}

function SummaryCard({ title, value, sub, subColor }: SummaryCardProps) {
  return (
    <Card className="min-w-0 p-4 sm:p-5">
      <CardTitle>{title}</CardTitle>
      <p className={cn('mt-2 whitespace-nowrap text-xl font-bold tracking-tight text-gray-900 tabular-nums 2xl:text-2xl', subColor)}>{value}</p>
      {sub && <p className={cn('mt-1 truncate text-sm font-medium', subColor ?? 'text-gray-500')}>{sub}</p>}
    </Card>
  )
}

type Props =
  | { summary: SummaryPayload; displayCurrency?: never; holdings?: never; hideZeroPrincipalMetrics?: never }
  | { summary: DashboardSummary; displayCurrency: DisplayCurrency; holdings?: never; hideZeroPrincipalMetrics?: boolean }
  | { holdings: Holding[]; summary?: never; displayCurrency?: never; hideZeroPrincipalMetrics?: never }

export function PortfolioSummary(props: Props) {
  if (props.summary) {
    if ('currencies' in props.summary) return <ScopedSummary summary={props.summary} />
    return (
      <DashboardSummaryCards
        summary={props.summary}
        displayCurrency={props.displayCurrency ?? 'KRW'}
        hideZeroPrincipalMetrics={props.hideZeroPrincipalMetrics ?? false}
      />
    )
  }
  return <LegacySummary holdings={props.holdings} />
}

function DashboardSummaryCards({
  summary,
  displayCurrency,
  hideZeroPrincipalMetrics,
}: {
  summary: DashboardSummary
  displayCurrency: DisplayCurrency
  hideZeroPrincipalMetrics: boolean
}) {
  const hidePrincipalMetrics = hideZeroPrincipalMetrics && parseNumeric(summary.total_invested_principal) === 0
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-5">
      {!hidePrincipalMetrics && (
        <SummaryCard title="투자원금" value={displayCurrencyValue(summary.total_invested_principal, displayCurrency)} />
      )}
      <SummaryCard title="잔여원금" value={displayCurrencyValue(summary.total_cost_basis, displayCurrency)} />
      <SummaryCard title="평가금액" value={displayCurrencyValue(summary.total_current_value, displayCurrency)} />
      <SummaryCard
        title="전일대비"
        value={displayCurrencyValue(summary.total_current_value_change, displayCurrency)}
        sub={summary.total_current_value_change_pct == null ? undefined : formatPercent(summary.total_current_value_change_pct)}
        subColor={profitColor(summary.total_current_value_change)}
      />
      <SummaryCard
        title="평가손익"
        value={displayCurrencyValue(summary.total_unrealized_profit_loss, displayCurrency)}
        sub={formatPercent(summary.total_unrealized_profit_loss_pct)}
        subColor={profitColor(summary.total_unrealized_profit_loss)}
      />
      {!hidePrincipalMetrics && (
        <>
          <SummaryCard
            title="총손익"
            value={displayCurrencyValue(summary.total_profit_loss, displayCurrency)}
            sub="평가금액 - 투자원금"
            subColor={profitColor(summary.total_profit_loss)}
          />
          <SummaryCard
            title="총손익률"
            value={formatPercent(summary.total_profit_loss_pct)}
            subColor={profitColor(summary.total_profit_loss_pct)}
          />
        </>
      )}
    </div>
  )
}

function ScopedSummary({ summary }: { summary: SummaryPayload }) {
  const groups = (Object.entries(summary.currencies) as Array<[Currency, PortfolioCurrencySummary]>)
    .filter(([, currencySummary]) => currencySummary !== undefined)

  if (groups.length === 0) {
    return <p className="rounded-xl border border-dashed border-gray-300 py-8 text-center text-sm text-gray-400">표시할 자산이 없습니다.</p>
  }

  return (
    <div className="flex flex-col gap-4">
      {summary.accounting_status === 'requires_review' && (
        <p className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-700">거래 분류 검토가 필요합니다.</p>
      )}
      {summary.warnings.length > 0 && (
        <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {summary.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      )}
      {groups.map(([currency, currencySummary]) => (
        <div key={currency}>
          <p className="mb-2 text-xs font-semibold text-gray-400">{currency}</p>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <SummaryCard title="투자원금" value={displayCurrency(currencySummary.total_invested_principal, currency)} />
            <SummaryCard title="잔여원금" value={displayCurrency(currencySummary.total_cost_basis, currency)} />
            <SummaryCard title="평가금액" value={displayCurrency(currencySummary.total_current_value, currency)} />
            <SummaryCard
              title="평가손익"
              value={displayCurrency(currencySummary.total_profit_loss, currency)}
              subColor={profitColor(currencySummary.total_profit_loss)}
            />
            <SummaryCard
              title="수익률"
              value={formatPercent(currencySummary.total_profit_loss_pct)}
              subColor={profitColor(currencySummary.total_profit_loss_pct)}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function displayCurrency(value: string | null, currency: Currency) {
  return value === null ? '—' : formatCurrency(value, currency)
}

function displayCurrencyValue(value: string | null, currency: DisplayCurrency) {
  return value === null ? '—' : formatCurrency(value, currency)
}

function parseNumeric(value: string | null) {
  if (value === null) return null
  const numeric = parseFloat(value)
  return Number.isFinite(numeric) ? numeric : null
}

function LegacySummary({ holdings }: { holdings: Holding[] }) {
  const active = holdings.filter((holding) => holding.is_active)
  const groups = (['KRW', 'USD'] as const)
    .map((currency) => ({ currency, holdings: active.filter((holding) => holding.currency === currency) }))
    .filter(({ holdings: currencyHoldings }) => currencyHoldings.length > 0)

  if (groups.length === 0) return <LegacyCurrencySummary currency="KRW" holdings={[]} />

  return (
    <div className="flex flex-col gap-4">
      {groups.map(({ currency, holdings: currencyHoldings }) => (
        <div key={currency}>
          {groups.length > 1 && <p className="mb-2 text-xs font-semibold text-gray-400">{currency}</p>}
          <LegacyCurrencySummary currency={currency} holdings={currencyHoldings} />
        </div>
      ))}
    </div>
  )
}

function LegacyCurrencySummary({ currency, holdings }: { currency: Currency; holdings: Holding[] }) {
  const totalCost = holdings.reduce((sum, holding) => sum + parseFloat(holding.cost_basis ?? '0'), 0)
  const totalValue = holdings.reduce((sum, holding) => sum + parseFloat(holding.current_value ?? holding.cost_basis ?? '0'), 0)
  const totalProfit = totalValue - totalCost
  const profitPct = totalCost > 0 ? totalProfit / totalCost * 100 : 0
  const hasPrices = holdings.length > 0 && holdings.every((holding) => holding.current_price !== null)

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <SummaryCard title="총 투자원금" value={formatCurrency(totalCost, currency)} />
      <SummaryCard title="총 평가금액" value={hasPrices ? formatCurrency(totalValue, currency) : '—'} sub={hasPrices ? undefined : '시세 로딩 중'} />
      <SummaryCard title="평가손익" value={hasPrices ? formatCurrency(totalProfit, currency) : '—'} subColor={profitColor(totalProfit)} />
      <SummaryCard title="수익률" value={hasPrices ? formatPercent(profitPct) : '—'} subColor={profitColor(profitPct)} />
    </div>
  )
}
