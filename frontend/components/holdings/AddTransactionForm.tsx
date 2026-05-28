'use client'

import { useState } from 'react'
import { holdingsApi } from '@/lib/api'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { today } from '@/lib/utils'

interface Props {
  holdingId: string
  onSuccess: () => void
}

export function AddTransactionForm({ holdingId, onSuccess }: Props) {
  const [type, setType] = useState<'BUY' | 'SELL'>('BUY')
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')
  const [txDate, setTxDate] = useState(today())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await holdingsApi.addTransaction(holdingId, { type, quantity, price, transaction_date: txDate })
      setQuantity('')
      setPrice('')
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
      <Button type="submit" loading={loading}>추가</Button>
      {error && <p className="w-full text-xs text-red-500">{error}</p>}
    </form>
  )
}
