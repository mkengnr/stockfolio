'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import useSWR from 'swr'
import { LabelMultiSelect } from '@/components/groups/LabelMultiSelect'
import { SellLotAllocationEditor } from '@/components/groups/SellLotAllocationEditor'
import { SourceGroupSelect } from '@/components/groups/SourceGroupSelect'
import { holdingsApi, fetcher } from '@/lib/api'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { compareFixedDecimals, isPositiveFixedDecimal, sumFixedDecimals } from '@/lib/fixedDecimal'
import { today } from '@/lib/utils'
import type { BuyLot, Currency, Label, SourceGroup } from '@/lib/types'

interface Props {
  holdingId: string
  currency?: Currency
  onSuccess: () => void
}

export function AddTransactionForm({ holdingId, currency = 'KRW', onSuccess }: Props) {
  const {
    data: sourceGroups = [],
    error: sourceGroupsError,
    isLoading: sourceGroupsLoading,
  } = useSWR<SourceGroup[]>('/api/groups/sources', fetcher)
  const {
    data: labels = [],
    error: labelsError,
    isLoading: labelsLoading,
  } = useSWR<Label[]>('/api/groups/labels', fetcher)
  const [type, setType] = useState<'BUY' | 'SELL'>('BUY')
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')
  const [txDate, setTxDate] = useState(today())
  const [sourceGroupId, setSourceGroupId] = useState<string | null>(null)
  const [labelIds, setLabelIds] = useState<string[]>([])
  const [lots, setLots] = useState<BuyLot[]>([])
  const [allocations, setAllocations] = useState<Record<string, string>>({})
  const [lotsLoading, setLotsLoading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const latestLotsRequest = useRef(0)
  const metadataLoading = sourceGroupsLoading || labelsLoading
  const metadataError = sourceGroupsError || labelsError
  const allocatedQuantity = sumFixedDecimals(Object.values(allocations).filter(isPositiveFixedDecimal)) ?? '0'
  const recommendedLabels = labels.filter((label) => (
    !labelIds.includes(label.id)
    && lots.some((lot) => isPositiveFixedDecimal(allocations[lot.id] ?? '') && lot.label_ids.includes(label.id))
  ))

  const loadLots = useCallback(async () => {
    const requestId = ++latestLotsRequest.current
    setLotsLoading(true)
    try {
      const nextLots = await holdingsApi.listLots(
        holdingId,
        sourceGroupId
          ? { scope_kind: 'source', scope_id: sourceGroupId }
          : { scope_kind: 'unclassified' },
      )
      if (requestId === latestLotsRequest.current) setLots(nextLots)
    } catch (err) {
      if (requestId === latestLotsRequest.current) {
        setLots([])
        setError(err instanceof Error ? err.message : '매수 lot을 불러오지 못했습니다.')
      }
    } finally {
      if (requestId === latestLotsRequest.current) setLotsLoading(false)
    }
  }, [holdingId, sourceGroupId])

  useEffect(() => {
    setAllocations({})
    if (type === 'SELL') {
      void loadLots()
    } else {
      latestLotsRequest.current += 1
      setLots([])
      setLotsLoading(false)
    }
  }, [loadLots, type])

  function updateAllocation(lotId: string, value: string) {
    setAllocations((current) => ({ ...current, [lotId]: value }))
  }

  function addRecommendedLabel(labelId: string) {
    setLabelIds((current) => current.includes(labelId) ? current : [...current, labelId])
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (metadataLoading) {
      setError('출처/라벨 정보를 불러오는 중입니다.')
      return
    }
    if (metadataError) {
      setError('출처/라벨 정보를 불러오지 못했습니다.')
      return
    }
    const sellAllocations = Object.entries(allocations)
      .filter(([, allocationQuantity]) => isPositiveFixedDecimal(allocationQuantity))
      .map(([buyLotId, allocatedQuantity]) => ({ buy_lot_id: buyLotId, quantity: allocatedQuantity }))

    if (type === 'SELL') {
      const sellAllocatedQuantity = sumFixedDecimals(sellAllocations.map((allocation) => allocation.quantity))
      if (sellAllocatedQuantity === null || compareFixedDecimals(sellAllocatedQuantity, quantity) !== 0) {
        setError('매도 수량과 lot 배분 합계가 일치해야 합니다.')
        return
      }
      const lotsById = new Map(lots.map((lot) => [lot.id, lot]))
      if (sellAllocations.some((allocation) => {
        const comparison = compareFixedDecimals(
          allocation.quantity,
          lotsById.get(allocation.buy_lot_id)?.remaining_quantity ?? '',
        )
        return comparison === null || comparison > 0
      })) {
        setError('lot 잔여 수량보다 많이 배분할 수 없습니다.')
        return
      }
    }

    setLoading(true)
    try {
      await holdingsApi.addTransaction(holdingId, {
        type,
        quantity,
        price,
        transaction_date: txDate,
        source_group_id: sourceGroupId,
        label_ids: labelIds,
        sell_allocations: type === 'SELL' ? sellAllocations : [],
      })
      setQuantity('')
      setPrice('')
      setAllocations({})
      if (type === 'SELL') await loadLots()
      onSuccess()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '거래 추가 오류')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
      <div className="flex rounded-lg border border-gray-300 overflow-hidden">
        {(['BUY', 'SELL'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setType(t)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              type === t
                ? t === 'BUY' ? 'bg-brand-500 text-white' : 'bg-red-500 text-white'
                : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            {t === 'BUY' ? '매수' : '매도'}
          </button>
        ))}
      </div>
      <Input
        label="수량"
        type="number"
        min="0"
        step="any"
        placeholder="10"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        required
        className="w-28"
      />
      <Input
        label="단가"
        type="number"
        min="0"
        step="any"
        placeholder="75000"
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        required
        className="w-32"
      />
      <Input
        label="날짜"
        type="date"
        value={txDate}
        max={today()}
        onChange={(e) => setTxDate(e.target.value)}
        required
        className="w-40"
      />
      <SourceGroupSelect groups={sourceGroups} value={sourceGroupId} onChange={setSourceGroupId} />
      <Button type="submit" loading={loading} disabled={metadataLoading || Boolean(metadataError)}>추가</Button>
      <div className="w-full">
        <LabelMultiSelect labels={labels} selectedIds={labelIds} onChange={setLabelIds} />
      </div>
      {recommendedLabels.length > 0 && (
        <div className="w-full rounded-lg border border-brand-100 bg-brand-50 p-3">
          <p className="mb-2 text-sm font-medium text-gray-700">선택 lot 추천 라벨</p>
          <div className="flex flex-wrap gap-2">
            {recommendedLabels.map((label) => (
              <button
                key={label.id}
                type="button"
                aria-label={`추천 추가: ${label.name}`}
                onClick={() => addRecommendedLabel(label.id)}
                className="rounded-full border border-brand-200 bg-white px-3 py-1 text-xs font-medium text-brand-700 hover:bg-brand-100"
              >
                + {label.name}
              </button>
            ))}
          </div>
        </div>
      )}
      {type === 'SELL' && (
        <>
          <SellLotAllocationEditor
            lots={lots}
            allocations={allocations}
            currency={currency}
            loading={lotsLoading}
            onChange={updateAllocation}
          />
          <p className="w-full text-sm font-medium text-gray-600">
            배분 합계 {allocatedQuantity} / 매도 수량 {quantity || '0'}
          </p>
        </>
      )}
      {metadataError && <p className="w-full text-xs text-red-500">출처/라벨 정보를 불러오지 못했습니다.</p>}
      {error && <p className="w-full text-xs text-red-500">{error}</p>}
    </form>
  )
}
