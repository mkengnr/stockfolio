'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { LabelMultiSelect } from '@/components/groups/LabelMultiSelect'
import { SourceGroupSelect } from '@/components/groups/SourceGroupSelect'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { holdingsApi, stocksApi, fetcher } from '@/lib/api'
import { today } from '@/lib/utils'
import type { Label, SourceGroup, StockSearchResult } from '@/lib/types'

export function HoldingForm() {
  const router = useRouter()
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

  const [ticker, setTicker] = useState('')
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')
  const [txDate, setTxDate] = useState(today())
  const [notes, setNotes] = useState('')
  const [sourceGroupId, setSourceGroupId] = useState<string | null>(null)
  const [labelIds, setLabelIds] = useState<string[]>([])
  const [searchResults, setSearchResults] = useState<StockSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const metadataLoading = sourceGroupsLoading || labelsLoading
  const metadataError = sourceGroupsError || labelsError

  const normalizedTicker = ticker.trim()
  const market = /^\d{6}$/.test(normalizedTicker)
    ? 'KRX'
    : /^[A-Za-z][A-Za-z0-9.-]*$/.test(normalizedTicker)
      ? 'US'
      : null

  useEffect(() => {
    const query = ticker.trim()
    if (!query) {
      setSearchResults([])
      return
    }

    const timer = window.setTimeout(async () => {
      setSearching(true)
      try {
        setSearchResults(await stocksApi.search(query))
      } catch {
        setSearchResults([])
      } finally {
        setSearching(false)
      }
    }, 250)

    return () => window.clearTimeout(timer)
  }, [ticker])

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
    setLoading(true)
    try {
      await holdingsApi.create({
        ticker: ticker.trim().toUpperCase(),
        quantity,
        price,
        transaction_date: txDate,
        notes: notes.trim() || undefined,
        source_group_id: sourceGroupId,
        label_ids: labelIds,
      })
      router.push('/')
      router.refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '등록 중 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="max-w-lg">
      <h2 className="mb-6 text-lg font-semibold text-gray-900">종목 등록</h2>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <Input
            label="종목 코드 또는 종목명"
            placeholder="005930, 삼성전자 또는 AAPL"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            required
            hint={market ? (market === 'KRX' ? '🇰🇷 한국 주식 (KRX)' : '🇺🇸 해외 주식 (US)') : undefined}
          />
        </div>
        {(searching || searchResults.length > 0) && (
          <div className="-mt-3 rounded-lg border border-gray-200 bg-white p-2 shadow-sm">
            {searching ? (
              <p className="px-2 py-1 text-xs text-gray-400">종목 검색 중...</p>
            ) : (
              searchResults.map((stock) => (
                <button
                  key={`${stock.market}:${stock.ticker}`}
                  type="button"
                  onClick={() => {
                    setTicker(stock.ticker)
                    setSearchResults([])
                  }}
                  className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-sm hover:bg-gray-50"
                >
                  <span className="font-medium text-gray-900">{stock.name}</span>
                  <span className="text-xs text-gray-400">{stock.ticker} · {stock.market}</span>
                </button>
              ))
            )}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="매수 수량"
            type="number"
            placeholder="10"
            min="0"
            step="any"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            required
          />
          <Input
            label="매수 단가"
            type="number"
            placeholder="75000"
            min="0"
            step="any"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            required
          />
        </div>

        <Input
          label="매수일"
          type="date"
          value={txDate}
          max={today()}
          onChange={(e) => setTxDate(e.target.value)}
          required
        />

        <Input
          label="메모 (선택)"
          placeholder="장기 보유, 분할매수 등"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />

        <SourceGroupSelect groups={sourceGroups} value={sourceGroupId} onChange={setSourceGroupId} />
        <LabelMultiSelect labels={labels} selectedIds={labelIds} onChange={setLabelIds} />

        {metadataError && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">출처/라벨 정보를 불러오지 못했습니다.</p>}
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

        <div className="flex gap-3 pt-2">
          <Button type="submit" loading={loading} disabled={metadataLoading || Boolean(metadataError)} className="flex-1">
            등록하기
          </Button>
          <Button type="button" variant="secondary" onClick={() => router.back()}>
            취소
          </Button>
        </div>
      </form>
    </Card>
  )
}
