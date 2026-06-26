import { formatCurrency, formatDate, formatNumber } from '@/lib/utils'
import { Badge } from '@/components/ui/Badge'
import type { Currency, SharedHoldingTransaction } from '@/lib/types'

export function SharedTransactionTable({
  transactions, currency,
}: { transactions: SharedHoldingTransaction[]; currency: Currency }) {
  if (transactions.length === 0) {
    return <p className="text-sm text-gray-400">거래 내역이 없습니다.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium uppercase text-gray-500">
            <th scope="col" className="px-3 py-2">구분</th>
            <th scope="col" className="px-3 py-2">날짜</th>
            <th scope="col" className="px-3 py-2 text-right">수량</th>
            <th scope="col" className="px-3 py-2 text-right">단가</th>
            <th scope="col" className="px-3 py-2 text-right">금액</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {transactions.map((tx, index) => (
            <tr key={`${index}-${tx.transaction_date}`} className="hover:bg-gray-50">
              <td className="px-3 py-2"><Badge color={tx.type === 'BUY' ? '#16a34a' : '#dc2626'}>{tx.type === 'BUY' ? '매수' : '매도'}</Badge></td>
              <td className="px-3 py-2 text-gray-700">{formatDate(tx.transaction_date)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-gray-700">{formatNumber(parseFloat(tx.quantity), 0)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-gray-700">{formatCurrency(tx.price, currency)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-gray-700">{formatCurrency(parseFloat(tx.quantity) * parseFloat(tx.price), currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
