'use client'

import { useState } from 'react'
import { holdingsApi } from '@/lib/api'
import { formatCurrency, formatDate, formatNumber } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import type { Transaction, Currency } from '@/lib/types'

interface Props {
  holdingId: string
  transactions: Transaction[]
  currency: Currency
  onRefresh: () => void
}

export function TransactionList({ holdingId, transactions, currency, onRefresh }: Props) {
  const [deleting, setDeleting] = useState<string | null>(null)

  async function handleDelete(txId: string) {
    if (!confirm('이 거래를 삭제하시겠습니까?')) return
    setDeleting(txId)
    try {
      await holdingsApi.deleteTransaction(holdingId, txId)
      onRefresh()
    } finally {
      setDeleting(null)
    }
  }

  if (transactions.length === 0) {
    return <p className="text-sm text-gray-400">거래 내역이 없습니다.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase">
            <th className="px-3 py-2">구분</th>
            <th className="px-3 py-2">날짜</th>
            <th className="px-3 py-2 text-right">수량</th>
            <th className="px-3 py-2 text-right">단가</th>
            <th className="px-3 py-2 text-right">금액</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {[...transactions]
            .sort((a, b) => b.transaction_date.localeCompare(a.transaction_date))
            .map((tx) => {
              const qty = parseFloat(tx.quantity)
              const price = parseFloat(tx.price)
              return (
                <tr key={tx.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block rounded px-1.5 py-0.5 text-xs font-semibold ${
                        tx.type === 'BUY'
                          ? 'bg-brand-50 text-brand-700'
                          : 'bg-red-50 text-red-600'
                      }`}
                    >
                      {tx.type === 'BUY' ? '매수' : '매도'}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-600">{formatDate(tx.transaction_date)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatNumber(qty, 0)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(price, currency)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(qty * price, currency)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={deleting === tx.id}
                      onClick={() => handleDelete(tx.id)}
                      className="text-red-400 hover:text-red-600"
                    >
                      삭제
                    </Button>
                  </td>
                </tr>
              )
            })}
        </tbody>
      </table>
    </div>
  )
}
