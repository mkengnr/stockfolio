'use client'

import Link from 'next/link'
import { useState } from 'react'
import { cn, formatCurrency, formatNumber, formatPercent, profitColor } from '@/lib/utils'
import type { Currency, Holding, ScopedPortfolioHolding } from '@/lib/types'

type TableHolding = Holding | ScopedPortfolioHolding
type SortKey = 'name' | 'profitPct' | 'currentValue' | 'profit'
type SortDir = 'asc' | 'desc'

interface Props {
  holdings: TableHolding[]
}

interface Row {
  key: string
  id: string | null
  ticker: string
  name: string
  subtitle: string
  currency: Currency
  quantity: string
  avgPrice: number
  currentPrice: string | null
  currentValue: string | null
  profit: string | null
  profitPct: number | null
}

function toRow(holding: TableHolding): Row {
  if ('remaining_quantity' in holding) {
    const quantity = parseFloat(holding.remaining_quantity)
    const cost = parseFloat(holding.remaining_cost_basis)
    const profit = holding.unrealized_profit_loss
    return {
      key: `${holding.currency}:${holding.ticker}`,
      id: null,
      ticker: holding.ticker,
      name: holding.name ?? holding.ticker,
      subtitle: `${holding.ticker} · ${holding.currency}`,
      currency: holding.currency,
      quantity: holding.remaining_quantity,
      avgPrice: quantity > 0 ? cost / quantity : 0,
      currentPrice: holding.current_price,
      currentValue: holding.current_value,
      profit,
      profitPct: profit === null || cost <= 0 ? null : parseFloat(profit) / cost * 100,
    }
  }
  return {
    key: holding.id,
    id: holding.id,
    ticker: holding.ticker,
    name: holding.name,
    subtitle: `${holding.ticker} · ${holding.market}`,
    currency: holding.currency,
    quantity: holding.quantity,
    avgPrice: parseFloat(holding.avg_price),
    currentPrice: holding.current_price,
    currentValue: holding.current_value,
    profit: holding.profit_loss,
    profitPct: holding.profit_loss_pct === null ? null : parseFloat(holding.profit_loss_pct),
  }
}

export function HoldingsTable({ holdings }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('profitPct')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((direction) => direction === 'asc' ? 'desc' : 'asc')
    else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sorted = holdings.map(toRow).sort((a, b) => {
    if (sortKey === 'name') return sortDir === 'asc' ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name)
    const left = sortKey === 'profitPct' ? a.profitPct : sortKey === 'currentValue' ? a.currentValue : a.profit
    const right = sortKey === 'profitPct' ? b.profitPct : sortKey === 'currentValue' ? b.currentValue : b.profit
    const leftNumber = typeof left === 'string' ? parseFloat(left) : left ?? 0
    const rightNumber = typeof right === 'string' ? parseFloat(right) : right ?? 0
    return sortDir === 'asc' ? leftNumber - rightNumber : rightNumber - leftNumber
  })

  function SortIcon({ column }: { column: SortKey }) {
    if (sortKey !== column) return <span className="ml-1 text-gray-300">↕</span>
    return <span className="ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  if (holdings.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 py-16 text-center">
        <p className="text-gray-400">보유 종목이 없습니다.</p>
        <Link href="/holdings/new" className="mt-2 inline-block text-sm text-brand-600 hover:underline">첫 종목 등록하기 →</Link>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50">
            <SortableHeading label="종목" align="left" onClick={() => toggleSort('name')}><SortIcon column="name" /></SortableHeading>
            <th className="px-4 py-3 text-right font-medium text-gray-500">수량</th>
            <th className="px-4 py-3 text-right font-medium text-gray-500">평균매수가</th>
            <th className="px-4 py-3 text-right font-medium text-gray-500">현재가</th>
            <SortableHeading label="평가금액" onClick={() => toggleSort('currentValue')}><SortIcon column="currentValue" /></SortableHeading>
            <SortableHeading label="손익" onClick={() => toggleSort('profit')}><SortIcon column="profit" /></SortableHeading>
            <SortableHeading label="수익률" onClick={() => toggleSort('profitPct')}><SortIcon column="profitPct" /></SortableHeading>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {sorted.map((row) => (
            <tr key={row.key} className="transition-colors hover:bg-gray-50">
              <td className="px-4 py-3">{row.id ? <HoldingName row={row} linked /> : <HoldingName row={row} />}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{formatNumber(row.quantity, 0)}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{formatCurrency(row.avgPrice, row.currency)}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{row.currentPrice ? formatCurrency(row.currentPrice, row.currency) : '—'}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{row.currentValue ? formatCurrency(row.currentValue, row.currency) : '—'}</td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(row.profit))}>{row.profit ? formatCurrency(row.profit, row.currency) : '—'}</td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(row.profitPct))}>{formatPercent(row.profitPct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SortableHeading({ label, align = 'right', onClick, children }: { label: string; align?: 'left' | 'right'; onClick: () => void; children: React.ReactNode }) {
  return (
    <th className={cn('cursor-pointer px-4 py-3 font-medium text-gray-500 hover:text-gray-700', align === 'left' ? 'text-left' : 'text-right')} onClick={onClick}>
      {label} {children}
    </th>
  )
}

function HoldingName({ row, linked }: { row: Row; linked?: boolean }) {
  const content = (
    <>
      <span className="font-medium text-gray-900 group-hover:text-brand-600">{row.name}</span>
      <span className="text-xs text-gray-400">{row.subtitle}</span>
    </>
  )
  return linked
    ? <Link href={`/holdings/${row.id}`} className="group flex flex-col">{content}</Link>
    : <div className="flex flex-col">{content}</div>
}
