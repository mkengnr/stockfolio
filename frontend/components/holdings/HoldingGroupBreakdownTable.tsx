import { Card } from '@/components/ui/Card'
import { formatCurrency, formatPercent, profitColor } from '@/lib/utils'
import type { Currency, SharedHoldingGroupBreakdown } from '@/lib/types'

export function HoldingGroupBreakdownTable({
  groupBreakdown, currency,
}: { groupBreakdown: SharedHoldingGroupBreakdown[]; currency: Currency }) {
  if (groupBreakdown.length === 0) {
    return (
      <Card>
        <h2 className="font-semibold text-gray-900">그룹별 수익현황</h2>
        <p className="mt-2 text-sm text-gray-500">현재 보유 중인 그룹별 잔여 수량이 없습니다.</p>
      </Card>
    )
  }

  return (
    <Card>
      <h2 className="mb-4 font-semibold text-gray-900">그룹별 수익현황</h2>
      <div className="overflow-x-auto">
        <table className="min-w-[900px] divide-y divide-gray-100 text-sm">
          <thead>
            <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
              <th className="px-3 py-2">그룹</th>
              <th className="px-3 py-2 text-right">수량</th>
              <th className="px-3 py-2 text-right">투자원금</th>
              <th className="px-3 py-2 text-right">잔여원금</th>
              <th className="px-3 py-2 text-right">평가금액</th>
              <th className="px-3 py-2 text-right">손익</th>
              <th className="px-3 py-2 text-right">손익률</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {groupBreakdown.map((group, index) => (
              <tr key={`${index}-${group.name}`} className="hover:bg-gray-50">
                <td className="px-3 py-3">
                  <span className="inline-flex items-center gap-2 font-medium text-gray-900">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: group.color ?? '#9ca3af' }}
                    />
                    {group.name}
                  </span>
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {parseFloat(group.remaining_quantity).toLocaleString()}주
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {formatCurrency(group.invested_principal, currency)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {formatCurrency(group.remaining_cost_basis, currency)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums">
                  {group.current_value ? formatCurrency(group.current_value, currency) : '—'}
                </td>
                <td className={`px-3 py-3 text-right tabular-nums font-medium ${profitColor(group.profit_loss)}`}>
                  {group.profit_loss ? formatCurrency(group.profit_loss, currency) : '—'}
                </td>
                <td className={`px-3 py-3 text-right tabular-nums font-medium ${profitColor(group.profit_loss_pct)}`}>
                  {formatPercent(group.profit_loss_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
