'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import type { SourceGroup, TransactionFilters as TransactionFiltersValue } from '@/lib/types'

interface Props {
  sourceGroups: SourceGroup[]
  filters: TransactionFiltersValue
  onApply: (filters: TransactionFiltersValue) => void
}

export function TransactionFilters({ sourceGroups, filters, onApply }: Props) {
  const [draft, setDraft] = useState<TransactionFiltersValue>(filters)

  function update<K extends keyof TransactionFiltersValue>(key: K, value: TransactionFiltersValue[K] | '') {
    setDraft((current) => {
      const next = { ...current }
      if (value === '') delete next[key]
      else next[key] = value as TransactionFiltersValue[K]
      return next
    })
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onApply(draft)
  }

  function resetFilters() {
    setDraft({})
    onApply({})
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-3 rounded-xl border border-gray-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-4">
      <Input
        id="transaction-date-from"
        type="date"
        label="시작일"
        value={draft.date_from ?? ''}
        onChange={(event) => update('date_from', event.target.value)}
      />
      <Input
        id="transaction-date-to"
        type="date"
        label="종료일"
        value={draft.date_to ?? ''}
        onChange={(event) => update('date_to', event.target.value)}
      />
      <Input
        id="transaction-query"
        label="검색어"
        placeholder="종목명 또는 티커"
        value={draft.q ?? ''}
        onChange={(event) => update('q', event.target.value)}
      />
      <div className="flex flex-col gap-1">
        <label htmlFor="transaction-type" className="text-sm font-medium text-gray-700">주문 필터</label>
        <select
          id="transaction-type"
          value={draft.type ?? ''}
          onChange={(event) => update('type', event.target.value as TransactionFiltersValue['type'] | '')}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">전체</option>
          <option value="BUY">매수</option>
          <option value="SELL">매도</option>
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="transaction-principal-flow" className="text-sm font-medium text-gray-700">투자원금처리 필터</label>
        <select
          id="transaction-principal-flow"
          value={draft.principal_flow ?? ''}
          onChange={(event) => update('principal_flow', event.target.value as TransactionFiltersValue['principal_flow'] | '')}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">전체</option>
          <option value="DEPOSIT">입금</option>
          <option value="REINVEST">재투자</option>
          <option value="WITHDRAW">출금</option>
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="transaction-review" className="text-sm font-medium text-gray-700">검토 상태</label>
        <select
          id="transaction-review"
          value={draft.requires_review ?? ''}
          onChange={(event) => update('requires_review', event.target.value as TransactionFiltersValue['requires_review'] | '')}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">전체</option>
          <option value="true">검토 필요</option>
          <option value="false">정상</option>
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="transaction-source-group" className="text-sm font-medium text-gray-700">그룹 필터</label>
        <select
          id="transaction-source-group"
          value={draft.source_group_id ?? ''}
          onChange={(event) => update('source_group_id', event.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">전체</option>
          {sourceGroups.map((group) => (
            <option key={group.id} value={group.id}>{group.name}</option>
          ))}
        </select>
      </div>
      <div className="flex items-end gap-2">
        <Button type="submit" size="md">필터 적용</Button>
        <Button type="button" variant="secondary" size="md" onClick={resetFilters}>초기화</Button>
      </div>
    </form>
  )
}
