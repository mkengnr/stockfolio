'use client'

import Link from 'next/link'
import { useState } from 'react'
import { cn, formatCurrency, formatNumber, formatPercent, profitColor } from '@/lib/utils'
import type { Holding } from '@/lib/types'

type SortKey = 'name' | 'profit_loss_pct' | 'current_value' | 'profit_loss'
type SortDir = 'asc' | 'desc'

interface Props {
  holdings: Holding[]
}

export function HoldingsTable({ holdings }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('profit_loss_pct')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sorted = [...holdings].sort((a, b) => {
    let av: number, bv: number
    if (sortKey === 'name') {
      return sortDir === 'asc'
        ? a.name.localeCompare(b.name)
        : b.name.localeCompare(a.name)
    }
    av = parseFloat(a[sortKey] ?? '0')
    bv = parseFloat(b[sortKey] ?? '0')
    return sortDir === 'asc' ? av - bv : bv - av
  })

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <span className="ml-1 text-gray-300">↕</span>
    return <span className="ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  if (holdings.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 py-16 text-center">
        <p className="text-gray-400">보유 종목이 없습니다.</p>
        <Link href="/holdings/new" className="mt-2 inline-block text-sm text-brand-600 hover:underline">
          첫 종목 등록하기 →
        </Link>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50">
            <th
              className="cursor-pointer px-4 py-3 text-left font-medium text-gray-500 hover:text-gray-700"
              onClick={() => toggleSort('name')}
            >
              종목 <SortIcon col="name" />
            </th>
            <th className="px-4 py-3 text-right font-medium text-gray-500">수량</th>
            <th className="px-4 py-3 text-right font-medium text-gray-500">평균매수가</th>
            <th className="px-4 py-3 text-right font-medium text-gray-500">현재가</th>
            <th
              className="cursor-pointer px-4 py-3 text-right font-medium text-gray-500 hover:text-gray-700"
              onClick={() => toggleSort('current_value')}
            >
              평가금액 <SortIcon col="current_value" />
            </th>
            <th
              className="cursor-pointer px-4 py-3 text-right font-medium text-gray-500 hover:text-gray-700"
              onClick={() => toggleSort('profit_loss')}
            >
              손익 <SortIcon col="profit_loss" />
            </th>
            <th
              className="cursor-pointer px-4 py-3 text-right font-medium text-gray-500 hover:text-gray-700"
              onClick={() => toggleSort('profit_loss_pct')}
            >
              수익률 <SortIcon col="profit_loss_pct" />
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {sorted.map((h) => (
            <tr key={h.id} className="hover:bg-gray-50 transition-colors">
              <td className="px-4 py-3">
                <Link href={`/holdings/${h.id}`} className="group flex flex-col">
                  <span className="font-medium text-gray-900 group-hover:text-brand-600">
                    {h.name}
                  </span>
                  <span className="text-xs text-gray-400">
                    {h.ticker} · {h.market}
                  </span>
                </Link>
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                {formatNumber(h.quantity, 0)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                {formatCurrency(h.avg_price, h.currency)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                {h.current_price ? formatCurrency(h.current_price, h.currency) : '—'}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                {h.current_value ? formatCurrency(h.current_value, h.currency) : '—'}
              </td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(h.profit_loss))}>
                {h.profit_loss ? formatCurrency(h.profit_loss, h.currency) : '—'}
              </td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(h.profit_loss_pct))}>
                {formatPercent(h.profit_loss_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
