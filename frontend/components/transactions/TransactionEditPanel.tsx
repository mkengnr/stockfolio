'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { LabelMultiSelect } from '@/components/groups/LabelMultiSelect'
import { SourceGroupSelect } from '@/components/groups/SourceGroupSelect'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import type { Label, PrincipalFlow, SourceGroup, TransactionListItem, TransactionUpdatePayload } from '@/lib/types'

interface Props {
  transaction: TransactionListItem
  sourceGroups: SourceGroup[]
  labels: Label[]
  saving: boolean
  onCancel: () => void
  onSave: (id: string, payload: TransactionUpdatePayload) => Promise<void>
}

const principalFlowLabels: Record<PrincipalFlow, string> = {
  DEPOSIT: '입금',
  REINVEST: '재투자',
  WITHDRAW: '출금',
}

const principalFlowOptions: Record<TransactionListItem['type'], PrincipalFlow[]> = {
  BUY: ['DEPOSIT', 'REINVEST'],
  SELL: ['REINVEST', 'WITHDRAW'],
}

export function TransactionEditPanel({ transaction, sourceGroups, labels, saving, onCancel, onSave }: Props) {
  const [transactionDate, setTransactionDate] = useState(transaction.transaction_date)
  const [quantity, setQuantity] = useState(transaction.quantity)
  const [price, setPrice] = useState(transaction.price)
  const [principalFlow, setPrincipalFlow] = useState<PrincipalFlow>(transaction.principal_flow)
  const [sourceGroupId, setSourceGroupId] = useState<string | null>(transaction.source_group_id)
  const [labelIds, setLabelIds] = useState(transaction.label_ids)
  const [error, setError] = useState('')

  useEffect(() => {
    setTransactionDate(transaction.transaction_date)
    setQuantity(transaction.quantity)
    setPrice(transaction.price)
    setPrincipalFlow(transaction.principal_flow)
    setSourceGroupId(transaction.source_group_id)
    setLabelIds(transaction.label_ids)
    setError('')
  }, [transaction])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    const payload: TransactionUpdatePayload = {
      transaction_date: transactionDate,
      price,
      principal_flow: principalFlow,
      source_group_id: sourceGroupId,
      label_ids: labelIds,
    }
    if (transaction.type === 'BUY') payload.quantity = quantity

    try {
      await onSave(transaction.id, payload)
    } catch (err) {
      setError(err instanceof Error ? err.message : '거래를 저장하지 못했습니다.')
    }
  }

  return (
    <section className="rounded-xl border border-brand-100 bg-brand-50/40 p-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-gray-900">거래 수정</h2>
          <p className="mt-1 text-sm text-gray-500">
            {transaction.holding_name} {transaction.type === 'BUY' ? '매수' : '매도'} 거래를 수정합니다.
          </p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>닫기</Button>
      </div>

      {error && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

      <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Input
          id="edit-transaction-date"
          type="date"
          label="주문일"
          value={transactionDate}
          onChange={(event) => setTransactionDate(event.target.value)}
        />
        <Input
          id="edit-transaction-quantity"
          type="number"
          step="any"
          label="수량"
          value={quantity}
          disabled={transaction.type === 'SELL'}
          hint={transaction.type === 'SELL' ? '매도 수량은 수정할 수 없습니다.' : undefined}
          onChange={(event) => setQuantity(event.target.value)}
        />
        <Input
          id="edit-transaction-price"
          type="number"
          step="any"
          label="단가"
          value={price}
          onChange={(event) => setPrice(event.target.value)}
        />
        <div className="flex flex-col gap-1">
          <label htmlFor="edit-principal-flow" className="text-sm font-medium text-gray-700">투자원금처리</label>
          <select
            id="edit-principal-flow"
            value={principalFlow}
            onChange={(event) => setPrincipalFlow(event.target.value as PrincipalFlow)}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            {principalFlowOptions[transaction.type].map((value) => (
              <option key={value} value={value}>{principalFlowLabels[value]}</option>
            ))}
          </select>
        </div>
        <SourceGroupSelect
          id="edit-source-group"
          label="출처 그룹"
          groups={sourceGroups}
          value={sourceGroupId}
          onChange={setSourceGroupId}
        />
        <div className="sm:col-span-2 lg:col-span-3">
          <LabelMultiSelect labels={labels} selectedIds={labelIds} onChange={setLabelIds} />
        </div>
        <div className="flex gap-2 sm:col-span-2 lg:col-span-3">
          <Button type="submit" loading={saving}>저장</Button>
          <Button type="button" variant="secondary" onClick={onCancel}>취소</Button>
        </div>
      </form>
    </section>
  )
}
