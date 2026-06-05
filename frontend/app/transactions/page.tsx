'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { TransactionEditPanel } from '@/components/transactions/TransactionEditPanel'
import { TransactionFilters } from '@/components/transactions/TransactionFilters'
import { TransactionsTable } from '@/components/transactions/TransactionsTable'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { Button } from '@/components/ui/Button'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { fetcher, transactionsApi } from '@/lib/api'
import type {
  Label,
  SourceGroup,
  TransactionFilters as TransactionFiltersValue,
  TransactionListItem,
  TransactionListPayload,
  TransactionUpdatePayload,
} from '@/lib/types'

function TransactionsContent() {
  const [filters, setFilters] = useState<TransactionFiltersValue>({})
  const [editing, setEditing] = useState<TransactionListItem | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const transactionsPath = useMemo(() => transactionsApi.listPath(filters), [filters])

  const {
    data: payload,
    error,
    isLoading,
    mutate,
  } = useSWR<TransactionListPayload>(transactionsPath, fetcher)
  const { data: sourceGroups = [] } = useSWR<SourceGroup[]>('/api/groups/sources', fetcher)
  const { data: labels = [] } = useSWR<Label[]>('/api/groups/labels', fetcher)

  async function handleDelete(transaction: TransactionListItem) {
    if (!confirm(`${transaction.holding_name} 거래를 삭제하시겠습니까?`)) return
    setDeletingId(transaction.id)
    setMessage('')
    try {
      await transactionsApi.delete(transaction.id)
      if (editing?.id === transaction.id) setEditing(null)
      await mutate()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '거래를 삭제하지 못했습니다.')
    } finally {
      setDeletingId(null)
    }
  }

  async function handleSave(id: string, update: TransactionUpdatePayload) {
    setSavingId(id)
    setMessage('')
    try {
      await transactionsApi.update(id, update)
      setEditing(null)
      await mutate()
    } finally {
      setSavingId(null)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">전체 거래내역</h1>
          <p className="mt-1 text-sm text-gray-500">
            모든 종목의 매수·매도 거래를 한 곳에서 조회하고 분류와 기본 정보를 수정합니다.
          </p>
        </div>
        <Link href="/" className="text-sm font-medium text-brand-600 hover:underline">
          대시보드로 돌아가기
        </Link>
      </div>

      <TransactionFilters sourceGroups={sourceGroups} filters={filters} onApply={setFilters} />

      {message && <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{message}</p>}
      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">
          거래내역을 불러오지 못했습니다.
          <Button type="button" variant="ghost" size="sm" onClick={() => void mutate()} className="ml-2 text-red-600">
            다시 시도
          </Button>
        </div>
      )}

      {editing && (
        <TransactionEditPanel
          transaction={editing}
          sourceGroups={sourceGroups}
          labels={labels}
          saving={savingId === editing.id}
          onCancel={() => setEditing(null)}
          onSave={handleSave}
        />
      )}

      {isLoading || !payload ? (
        <PageLoader />
      ) : (
        <TransactionsTable
          transactions={payload.transactions}
          deletingId={deletingId}
          onEdit={setEditing}
          onDelete={handleDelete}
        />
      )}
    </div>
  )
}

export default function TransactionsPage() {
  return (
    <AuthGuard>
      <TransactionsContent />
    </AuthGuard>
  )
}
