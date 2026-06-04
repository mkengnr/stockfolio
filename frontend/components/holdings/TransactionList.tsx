'use client'

import { Fragment, useState } from 'react'
import useSWR from 'swr'
import { TransactionClassificationEditor } from '@/components/groups/TransactionClassificationEditor'
import { ReviewedSellRepairEditor } from '@/components/holdings/ReviewedSellRepairEditor'
import { holdingsApi, fetcher } from '@/lib/api'
import { formatCurrency, formatDate, formatNumber } from '@/lib/utils'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import type { Currency, Label, SourceGroup, Transaction } from '@/lib/types'

interface Props {
  holdingId: string
  transactions: Transaction[]
  currency: Currency
  onRefresh: () => void
}

export function TransactionList({ holdingId, transactions, currency, onRefresh }: Props) {
  const { data: sourceGroups = [] } = useSWR<SourceGroup[]>('/api/groups/sources', fetcher)
  const { data: labels = [] } = useSWR<Label[]>('/api/groups/labels', fetcher)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState('')

  async function handleDelete(txId: string) {
    if (!confirm('이 거래를 삭제하시겠습니까?')) return
    setDeleting(txId)
    setDeleteError('')
    try {
      await holdingsApi.deleteTransaction(holdingId, txId)
      onRefresh()
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : '거래를 삭제하지 못했습니다.')
    } finally {
      setDeleting(null)
    }
  }

  if (transactions.length === 0) {
    return <p className="text-sm text-gray-400">거래 내역이 없습니다.</p>
  }

  return (
    <>
      {deleteError && <p className="mb-3 text-sm text-red-500">{deleteError}</p>}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase">
            <th className="px-3 py-2">구분</th>
            <th className="px-3 py-2">날짜</th>
            <th className="px-3 py-2 text-right">수량</th>
            <th className="px-3 py-2 text-right">단가</th>
            <th className="px-3 py-2 text-right">금액</th>
            <th className="px-3 py-2">분류</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {[...transactions]
            .sort((a, b) => b.transaction_date.localeCompare(a.transaction_date))
            .map((tx) => {
              const qty = parseFloat(tx.quantity)
              const price = parseFloat(tx.price)
              const sourceGroup = sourceGroups.find((group) => group.id === tx.source_group_id)
              const sourceGroupName = tx.source_group_id === null ? '미분류' : sourceGroup?.name ?? '출처 확인 중'
              const transactionLabels = labels.filter((label) => tx.label_ids.includes(label.id))
              return (
                <Fragment key={tx.id}>
                  <tr className="hover:bg-gray-50">
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
                    <td className="px-3 py-2">
                      <div className="flex max-w-xs flex-wrap gap-1">
                        <Badge color={sourceGroup?.color}>{sourceGroupName}</Badge>
                        {transactionLabels.map((label) => <Badge key={label.id} color={label.color}>{label.name}</Badge>)}
                        {tx.requires_review && <Badge className="border-amber-200 bg-amber-50 text-amber-700">검토 필요</Badge>}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => setEditingId(tx.id)}>
                          {tx.type === 'SELL' && tx.requires_review ? '매도 검토' : '분류 수정'}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          loading={deleting === tx.id}
                          onClick={() => handleDelete(tx.id)}
                          className="text-red-400 hover:text-red-600"
                        >
                          삭제
                        </Button>
                      </div>
                    </td>
                  </tr>
                  {editingId === tx.id && (
                    <tr>
                      <td colSpan={7} className="px-3 py-3">
                        {tx.type === 'SELL' && tx.requires_review ? (
                          <ReviewedSellRepairEditor
                            holdingId={holdingId}
                            transaction={tx}
                            currency={currency}
                            onRefresh={onRefresh}
                            onCancel={() => setEditingId(null)}
                          />
                        ) : (
                          <TransactionClassificationEditor
                            holdingId={holdingId}
                            transactionId={tx.id}
                            sourceGroups={sourceGroups}
                            labels={labels}
                            sourceGroupId={tx.source_group_id}
                            labelIds={tx.label_ids}
                            onRefresh={onRefresh}
                            onCancel={() => setEditingId(null)}
                          />
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
        </tbody>
        </table>
      </div>
    </>
  )
}
