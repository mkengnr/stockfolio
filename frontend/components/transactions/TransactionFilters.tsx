'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { cn } from '@/lib/utils'
import type { SourceGroup, TransactionFilters as TransactionFiltersValue } from '@/lib/types'

interface Props {
  sourceGroups: SourceGroup[]
  filters: TransactionFiltersValue
  onApply: (filters: TransactionFiltersValue) => void
}

export function TransactionFilters({ sourceGroups, filters, onApply }: Props) {
  const [draft, setDraft] = useState<TransactionFiltersValue>(filters)
  const activeCount = Object.values(filters).filter((value) => value !== undefined && value !== '').length
  const [open, setOpen] = useState(activeCount > 0)

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
    setOpen(false)
  }

  function resetFilters() {
    setDraft({})
    onApply({})
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-sm font-medium text-gray-700"
      >
        <span className="flex items-center gap-2">
          필터
          {activeCount > 0 && (
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-500 px-1.5 text-xs font-semibold text-white">
              {activeCount}
            </span>
          )}
        </span>
        <span className={cn('text-gray-400 transition-transform', open && 'rotate-180')} aria-hidden>▾</span>
      </button>
      <form onSubmit={handleSubmit} className={cn('grid gap-3 border-t border-gray-100 p-4 sm:grid-cols-2 lg:grid-cols-4', !open && 'hidden')}>
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
    </div>
  )
}
