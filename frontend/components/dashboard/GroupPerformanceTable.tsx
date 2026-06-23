import { StickyScrollTable } from '@/components/ui/StickyScrollTable'
import { cn, formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { DashboardGroupKind, DashboardGroupSummary, DisplayCurrency } from '@/lib/types'

interface Props {
  groups: DashboardGroupSummary[]
  displayCurrency: DisplayCurrency
}

const kindLabels: Record<DashboardGroupKind, string> = {
  source: '원천',
  combined: '통합',
  unclassified: '분류 없음',
}

export function GroupPerformanceTable({ groups, displayCurrency }: Props) {
  if (groups.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 py-10 text-center text-sm text-gray-400">
        표시할 그룹 수익현황이 없습니다.
      </div>
    )
  }

  const sortedGroups = [...groups].sort(compareGroups)

  return (
    <StickyScrollTable className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="min-w-[980px] text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            <th className="sticky left-0 top-0 z-20 border-r border-gray-100 bg-gray-50 px-4 py-3 text-left font-medium text-gray-500">그룹</th>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-right font-medium text-gray-500">투자원금</th>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-right font-medium text-gray-500">잔여원금</th>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-right font-medium text-gray-500">평가금액</th>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-right font-medium text-gray-500">당일손익</th>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-right font-medium text-gray-500">평가손익</th>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-right font-medium text-gray-500">총손익</th>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-right font-medium text-gray-500">총손익률</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {sortedGroups.map((group) => (
            <tr key={`${group.kind}:${group.id ?? 'unclassified'}`} className="group/row hover:bg-gray-50">
              <td className="sticky left-0 z-10 border-r border-gray-100 bg-white px-4 py-3 group-hover/row:bg-gray-50">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-full border border-white shadow-sm"
                    style={{ backgroundColor: group.color ?? '#d1d5db' }}
                    aria-hidden
                  />
                  <div className="flex flex-col">
                    <span className="font-medium text-gray-900">{group.name}</span>
                    <span className="text-xs text-gray-400">{kindLabels[group.kind]}</span>
                  </div>
                </div>
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                {displayMoney(group.summary.total_invested_principal, displayCurrency)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                {displayMoney(group.summary.total_cost_basis, displayCurrency)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                {displayMoney(group.summary.total_current_value, displayCurrency)}
              </td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(group.summary.total_current_value_change))}>
                {displayMoney(group.summary.total_current_value_change, displayCurrency)}
              </td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(group.summary.total_unrealized_profit_loss))}>
                {displayMoney(group.summary.total_unrealized_profit_loss, displayCurrency)}
              </td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(group.summary.total_profit_loss))}>
                {displayMoney(group.summary.total_profit_loss, displayCurrency)}
              </td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(group.summary.total_profit_loss_pct))}>
                {formatPercent(group.summary.total_profit_loss_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </StickyScrollTable>
  )
}

function displayMoney(value: string | null, displayCurrency: DisplayCurrency) {
  return value === null ? '—' : formatCurrency(value, displayCurrency)
}

const groupKindOrder: Record<DashboardGroupKind, number> = {
  source: 1,
  combined: 2,
  unclassified: 3,
}

function compareGroups(left: DashboardGroupSummary, right: DashboardGroupSummary) {
  const kindDiff = groupKindOrder[left.kind] - groupKindOrder[right.kind]
  if (kindDiff !== 0) return kindDiff
  const nameDiff = left.name.localeCompare(right.name, 'ko')
  if (nameDiff !== 0) return nameDiff
  return (left.id ?? '').localeCompare(right.id ?? '')
}
