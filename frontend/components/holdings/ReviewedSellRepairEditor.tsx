'use client'

import { useCallback, useEffect, useState } from 'react'
import useSWR from 'swr'
import { LabelMultiSelect } from '@/components/groups/LabelMultiSelect'
import { SellLotAllocationEditor } from '@/components/groups/SellLotAllocationEditor'
import { SourceGroupSelect } from '@/components/groups/SourceGroupSelect'
import { Button } from '@/components/ui/Button'
import { compareFixedDecimals, isPositiveFixedDecimal, sumFixedDecimals } from '@/lib/fixedDecimal'
import { fetcher, holdingsApi } from '@/lib/api'
import type { BuyLot, Currency, Label, SourceGroup, Transaction } from '@/lib/types'

interface Props {
  holdingId: string
  transaction: Transaction
  currency: Currency
  onRefresh: () => void | Promise<unknown>
  onCancel: () => void
}

export function ReviewedSellRepairEditor({ holdingId, transaction, currency, onRefresh, onCancel }: Props) {
  const { data: sourceGroups = [], isLoading: sourcesLoading } = useSWR<SourceGroup[]>('/api/groups/sources', fetcher)
  const { data: labels = [], isLoading: labelsLoading } = useSWR<Label[]>('/api/groups/labels', fetcher)
  const [sourceGroupId, setSourceGroupId] = useState<string | null>(transaction.source_group_id)
  const [labelIds, setLabelIds] = useState<string[]>(transaction.label_ids)
  const [lots, setLots] = useState<BuyLot[]>([])
  const [allocations, setAllocations] = useState<Record<string, string>>({})
  const [lotsLoading, setLotsLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const allocatedQuantity = sumFixedDecimals(Object.values(allocations).filter(isPositiveFixedDecimal)) ?? '0'

  const loadLots = useCallback(async () => {
    setLotsLoading(true)
    setError('')
    try {
      setLots(await holdingsApi.listReviewLots(
        holdingId,
        transaction.id,
        sourceGroupId
          ? { scope_kind: 'source', scope_id: sourceGroupId }
          : { scope_kind: 'unclassified' },
      ))
    } catch (err) {
      setLots([])
      setError(err instanceof Error ? err.message : '과거 매수 lot을 불러오지 못했습니다.')
    } finally {
      setLotsLoading(false)
    }
  }, [holdingId, sourceGroupId, transaction.id])

  useEffect(() => {
    setAllocations({})
    void loadLots()
  }, [loadLots])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    const sellAllocations = Object.entries(allocations)
      .filter(([, quantity]) => isPositiveFixedDecimal(quantity))
      .map(([buyLotId, quantity]) => ({ buy_lot_id: buyLotId, quantity }))
    const total = sumFixedDecimals(sellAllocations.map((allocation) => allocation.quantity))
    if (total === null || compareFixedDecimals(total, transaction.quantity) !== 0) {
      setError('매도 수량과 lot 배분 합계가 일치해야 합니다.')
      return
    }
    const lotsById = new Map(lots.map((lot) => [lot.id, lot]))
    if (sellAllocations.some((allocation) => {
      const comparison = compareFixedDecimals(allocation.quantity, lotsById.get(allocation.buy_lot_id)?.remaining_quantity ?? '')
      return comparison === null || comparison > 0
    })) {
      setError('lot 잔여 수량보다 많이 배분할 수 없습니다.')
      return
    }

    setSaving(true)
    try {
      await holdingsApi.repairReviewedSell(holdingId, transaction.id, {
        source_group_id: sourceGroupId,
        label_ids: labelIds,
        sell_allocations: sellAllocations,
      })
      await onRefresh()
      onCancel()
    } catch (err) {
      setError(err instanceof Error ? err.message : '매도 검토 내용을 저장하지 못했습니다.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
      <p className="text-sm text-amber-800">이전 매도 거래입니다. 자금 출처와 원 매수 lot을 확인해 주세요.</p>
      <SourceGroupSelect groups={sourceGroups} value={sourceGroupId} onChange={setSourceGroupId} />
      <LabelMultiSelect labels={labels} selectedIds={labelIds} onChange={setLabelIds} />
      <SellLotAllocationEditor lots={lots} allocations={allocations} currency={currency} loading={lotsLoading} onChange={(lotId, quantity) => setAllocations((current) => ({ ...current, [lotId]: quantity }))} />
      <p className="text-sm font-medium text-gray-600">배분 합계 {allocatedQuantity} / 매도 수량 {transaction.quantity}</p>
      <div className="flex gap-2">
        <Button type="submit" size="sm" loading={saving} disabled={sourcesLoading || labelsLoading || lotsLoading}>매도 검토 저장</Button>
        <Button type="button" size="sm" variant="secondary" onClick={onCancel}>취소</Button>
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </form>
  )
}
