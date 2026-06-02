'use client'

import { useEffect, useState } from 'react'
import { LabelMultiSelect } from '@/components/groups/LabelMultiSelect'
import { SourceGroupSelect } from '@/components/groups/SourceGroupSelect'
import { Button } from '@/components/ui/Button'
import { holdingsApi } from '@/lib/api'
import type { Label, SourceGroup } from '@/lib/types'

interface Props {
  holdingId: string
  transactionId: string
  sourceGroups: SourceGroup[]
  labels: Label[]
  sourceGroupId: string | null
  labelIds: string[]
  onRefresh: () => void | Promise<unknown>
  onCancel: () => void
}

export function TransactionClassificationEditor({
  holdingId,
  transactionId,
  sourceGroups,
  labels,
  sourceGroupId,
  labelIds,
  onRefresh,
  onCancel,
}: Props) {
  const [selectedSourceId, setSelectedSourceId] = useState(sourceGroupId)
  const [selectedLabelIds, setSelectedLabelIds] = useState(labelIds)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setSelectedSourceId(sourceGroupId)
    setSelectedLabelIds(labelIds)
  }, [labelIds, sourceGroupId])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      await holdingsApi.updateTransactionClassification(holdingId, transactionId, {
        source_group_id: selectedSourceId,
        label_ids: selectedLabelIds,
      })
      await onRefresh()
      onCancel()
    } catch (err) {
      setError(err instanceof Error ? err.message : '거래 분류를 변경하지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
      <SourceGroupSelect
        id={`classification-source-${transactionId}`}
        groups={sourceGroups}
        value={selectedSourceId}
        onChange={setSelectedSourceId}
      />
      <LabelMultiSelect labels={labels} selectedIds={selectedLabelIds} onChange={setSelectedLabelIds} />
      <div className="flex gap-2">
        <Button type="submit" size="sm" loading={loading}>분류 저장</Button>
        <Button type="button" size="sm" variant="secondary" onClick={onCancel}>취소</Button>
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </form>
  )
}
