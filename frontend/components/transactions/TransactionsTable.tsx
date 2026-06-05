'use client'

import Link from 'next/link'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { formatCurrency, formatDate, formatNumber } from '@/lib/utils'
import type { TransactionListItem } from '@/lib/types'

interface Props {
  transactions: TransactionListItem[]
  deletingId: string | null
  onEdit: (transaction: TransactionListItem) => void
  onDelete: (transaction: TransactionListItem) => void
}

const principalFlowLabels: Record<TransactionListItem['principal_flow'], string> = {
  DEPOSIT: '입금',
  REINVEST: '재투자',
  WITHDRAW: '출금',
}

export function TransactionsTable({ transactions, deletingId, onEdit, onDelete }: Props) {
  if (transactions.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-white px-6 py-10 text-center text-sm text-gray-500">
        조건에 맞는 거래내역이 없습니다.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase">
            <th className="px-3 py-2">주문일</th>
            <th className="px-3 py-2">종목</th>
            <th className="px-3 py-2">주문</th>
            <th className="px-3 py-2">그룹</th>
            <th className="px-3 py-2">투자원금처리</th>
            <th className="px-3 py-2 text-right">수량</th>
            <th className="px-3 py-2 text-right">단가</th>
            <th className="px-3 py-2 text-right">금액</th>
            <th className="px-3 py-2">라벨</th>
            <th className="px-3 py-2">상태</th>
            <th className="px-3 py-2 text-right">작업</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {transactions.map((transaction) => (
            <tr key={transaction.id} className="hover:bg-gray-50">
              <td className="whitespace-nowrap px-3 py-3 text-gray-600">{formatDate(transaction.transaction_date)}</td>
              <td className="px-3 py-3">
                <Link href={`/holdings/${transaction.holding_id}`} className="font-medium text-gray-900 hover:text-brand-600">
                  {transaction.holding_name}
                </Link>
                <p className="text-xs text-gray-400">{transaction.ticker}</p>
              </td>
              <td className="px-3 py-3">
                <span
                  className={`inline-block rounded px-1.5 py-0.5 text-xs font-semibold ${
                    transaction.type === 'BUY'
                      ? 'bg-brand-50 text-brand-700'
                      : 'bg-red-50 text-red-600'
                  }`}
                >
                  {transaction.type === 'BUY' ? '매수' : '매도'}
                </span>
              </td>
              <td className="px-3 py-3">
                <Badge>{transaction.source_group_name ?? '미분류'}</Badge>
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-gray-700">{principalFlowLabels[transaction.principal_flow]}</td>
              <td className="px-3 py-3 text-right tabular-nums">{formatNumber(transaction.quantity, 4)}</td>
              <td className="px-3 py-3 text-right tabular-nums">{formatCurrency(transaction.price, transaction.currency)}</td>
              <td className="px-3 py-3 text-right tabular-nums">{formatCurrency(transaction.amount, transaction.currency)}</td>
              <td className="px-3 py-3">
                <div className="flex max-w-xs flex-wrap gap-1">
                  {transaction.label_names.length === 0 ? (
                    <span className="text-xs text-gray-400">-</span>
                  ) : (
                    transaction.label_names.map((label) => <Badge key={label}>{label}</Badge>)
                  )}
                </div>
              </td>
              <td className="px-3 py-3">
                {transaction.requires_review ? (
                  <Badge className="border-amber-200 bg-amber-50 text-amber-700">검토 필요</Badge>
                ) : (
                  <Badge className="border-green-200 bg-green-50 text-green-700">정상</Badge>
                )}
              </td>
              <td className="px-3 py-3 text-right">
                <div className="flex justify-end gap-1">
                  <Button variant="ghost" size="sm" onClick={() => onEdit(transaction)}>수정</Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={deletingId === transaction.id}
                    onClick={() => onDelete(transaction)}
                    className="text-red-400 hover:text-red-600"
                  >
                    삭제
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
