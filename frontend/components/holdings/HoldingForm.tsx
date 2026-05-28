'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { holdingsApi, tagsApi, fetcher } from '@/lib/api'
import { detectMarket, today } from '@/lib/utils'
import type { Tag } from '@/lib/types'

export function HoldingForm() {
  const router = useRouter()
  const { data: tags } = useSWR<Tag[]>('/api/tags', fetcher)

  const [ticker, setTicker] = useState('')
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')
  const [txDate, setTxDate] = useState(today())
  const [notes, setNotes] = useState('')
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const market = ticker.trim() ? detectMarket(ticker) : null

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const holding = await holdingsApi.create({
        ticker: ticker.trim().toUpperCase(),
        quantity,
        price,
        transaction_date: txDate,
        notes: notes.trim() || undefined,
      })
      // attach tags
      await Promise.all(selectedTags.map((tid) => tagsApi.addHolding(holding.id, tid)))
      router.push('/')
      router.refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '등록 중 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  function toggleTag(id: string) {
    setSelectedTags((prev) => prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id])
  }

  return (
    <Card className="max-w-lg">
      <h2 className="mb-6 text-lg font-semibold text-gray-900">종목 등록</h2>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <Input
            label="종목 코드"
            placeholder="005930  또는  AAPL"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            required
            hint={market ? (market === 'KRX' ? '🇰🇷 한국 주식 (KRX)' : '🇺🇸 해외 주식 (US)') : undefined}
          />
        </div>

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

        {tags && tags.length > 0 && (
          <div>
            <p className="mb-2 text-sm font-medium text-gray-700">태그 선택 (선택)</p>
            <div className="flex flex-wrap gap-2">
              {tags.map((tag) => (
                <button
                  key={tag.id}
                  type="button"
                  onClick={() => toggleTag(tag.id)}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition-all ${
                    selectedTags.includes(tag.id) ? 'ring-2 ring-offset-1' : 'opacity-70 hover:opacity-100'
                  }`}
                  style={{
                    backgroundColor: `${tag.color}20`,
                    color: tag.color,
                    borderColor: `${tag.color}50`,
                    ...(selectedTags.includes(tag.id) ? { ringColor: tag.color } : {}),
                  }}
                >
                  {tag.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

        <div className="flex gap-3 pt-2">
          <Button type="submit" loading={loading} className="flex-1">
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
