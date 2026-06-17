'use client'

import Link from 'next/link'
import { useState } from 'react'
import { StickyScrollTable } from '@/components/ui/StickyScrollTable'
import { cn, formatCurrency, formatNumber, formatPercent, profitColor } from '@/lib/utils'
import type {
  Currency, DashboardHoldingGroupBadge, DashboardHoldingRow, DisplayCurrency, Holding,
  PublicScopedPortfolioHolding, ScopedPortfolioHolding,
} from '@/lib/types'

type TableHolding = Holding | PublicScopedPortfolioHolding | ScopedPortfolioHolding | DashboardHoldingRow
type SortKey = 'name' | 'profitPct' | 'currentValue' | 'profit'
type SortDir = 'asc' | 'desc'

interface Props {
  holdings: TableHolding[]
  displayCurrency?: DisplayCurrency
}

interface Row {
  key: string
  id: string | null
  ticker: string
  name: string
  subtitle: string
  priceCurrency: Currency
  valueCurrency: Currency
  quantity: string
  avgPrice: number
  currentPrice: string | null
  currentValue: string | null
  profit: string | null
  profitPct: number | null
  groups: DashboardHoldingGroupBadge[]
}

function toRow(holding: TableHolding, displayCurrency?: DisplayCurrency): Row {
  if ('groups' in holding) {
    const quantity = parseFloat(holding.quantity)
    const cost = parseNumeric(holding.remaining_cost_basis)
    const profit = holding.unrealized_profit_loss
    const valueCurrency = displayCurrency ?? holding.currency
    return {
      key: holding.holding_id || `${holding.currency}:${holding.ticker}`,
      id: holding.holding_id || null,
      ticker: holding.ticker,
      name: holding.name ?? holding.ticker,
      subtitle: `${holding.ticker} · ${holding.market}`,
      priceCurrency: holding.currency,
      valueCurrency,
      quantity: holding.quantity,
      avgPrice: quantity > 0 && cost !== null ? cost / quantity : 0,
      currentPrice: holding.current_price,
      currentValue: holding.current_value,
      profit,
      profitPct: profit === null || cost === null || cost <= 0 ? null : parseFloat(profit) / cost * 100,
      groups: holding.groups,
    }
  }
  if ('remaining_quantity' in holding) {
    const quantity = parseFloat(holding.remaining_quantity)
    const cost = parseNumeric(holding.remaining_cost_basis)
    const profit = holding.unrealized_profit_loss
    return {
      key: `${holding.currency}:${holding.ticker}`,
      id: 'holding_id' in holding ? holding.holding_id : null,
      ticker: holding.ticker,
      name: holding.name ?? holding.ticker,
      subtitle: `${holding.ticker} · ${holding.currency}`,
      priceCurrency: holding.currency,
      valueCurrency: holding.currency,
      quantity: holding.remaining_quantity,
      avgPrice: quantity > 0 && cost !== null ? cost / quantity : 0,
      currentPrice: holding.current_price,
      currentValue: holding.current_value,
      profit,
      profitPct: profit === null || cost === null || cost <= 0 ? null : parseFloat(profit) / cost * 100,
      groups: [],
    }
  }
  return {
    key: holding.id,
    id: holding.id,
    ticker: holding.ticker,
    name: holding.name,
    subtitle: `${holding.ticker} · ${holding.market}`,
    priceCurrency: holding.currency,
    valueCurrency: holding.currency,
    quantity: holding.quantity,
    avgPrice: parseFloat(holding.avg_price),
    currentPrice: holding.current_price,
    currentValue: holding.current_value,
    profit: holding.profit_loss,
    profitPct: holding.profit_loss_pct === null ? null : parseFloat(holding.profit_loss_pct),
    groups: [],
  }
}

export function HoldingsTable({ holdings, displayCurrency }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('profitPct')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((direction) => direction === 'asc' ? 'desc' : 'asc')
    else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sorted = holdings.map((holding) => toRow(holding, displayCurrency)).sort((a, b) => {
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
    <StickyScrollTable className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="min-w-[980px] text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            <SortableHeading label="종목" align="left" sticky onClick={() => toggleSort('name')}><SortIcon column="name" /></SortableHeading>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-left font-medium text-gray-500">그룹</th>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-right font-medium text-gray-500">수량</th>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-right font-medium text-gray-500">평균매수가</th>
            <th className="sticky top-0 z-10 bg-gray-50 px-4 py-3 text-right font-medium text-gray-500">현재가</th>
            <SortableHeading label="평가금액" onClick={() => toggleSort('currentValue')}><SortIcon column="currentValue" /></SortableHeading>
            <SortableHeading label="평가손익" onClick={() => toggleSort('profit')}><SortIcon column="profit" /></SortableHeading>
            <SortableHeading label="평가손익률" onClick={() => toggleSort('profitPct')}><SortIcon column="profitPct" /></SortableHeading>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {sorted.map((row) => (
            <tr key={row.key} className="group/row transition-colors hover:bg-gray-50">
              <td className="sticky left-0 z-10 border-r border-gray-100 bg-white px-4 py-3 group-hover/row:bg-gray-50">{row.id ? <HoldingName row={row} linked /> : <HoldingName row={row} />}</td>
              <td className="px-4 py-3"><GroupBadges groups={row.groups} /></td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{formatShareQuantity(row.quantity)}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{formatCurrency(row.avgPrice, row.valueCurrency)}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{row.currentPrice ? formatCurrency(row.currentPrice, row.priceCurrency) : '—'}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{row.currentValue ? formatCurrency(row.currentValue, row.valueCurrency) : '—'}</td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(row.profit))}>{row.profit ? formatCurrency(row.profit, row.valueCurrency) : '—'}</td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(row.profitPct))}>{formatPercent(row.profitPct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </StickyScrollTable>
  )
}

function GroupBadges({ groups }: { groups: DashboardHoldingGroupBadge[] }) {
  if (groups.length === 0) return <span className="text-gray-400">—</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {groups.map((group) => (
        <span
          key={`${group.source_group_id ?? 'unclassified'}:${group.name}`}
          className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700"
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: group.color ?? '#9ca3af' }}
            aria-hidden
          />
          {group.name} {formatShareQuantity(group.remaining_quantity)}주
        </span>
      ))}
    </div>
  )
}

function formatShareQuantity(quantity: string) {
  const numeric = parseFloat(quantity)
  if (!Number.isFinite(numeric)) return quantity
  return Number.isInteger(numeric) ? formatNumber(numeric, 0) : formatNumber(numeric, 2)
}

function parseNumeric(value: string | null) {
  if (value === null) return null
  const numeric = parseFloat(value)
  return Number.isFinite(numeric) ? numeric : null
}

function SortableHeading({ label, align = 'right', sticky = false, onClick, children }: { label: string; align?: 'left' | 'right'; sticky?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <th
      className={cn(
        'sticky top-0 z-10 cursor-pointer bg-gray-50 px-4 py-3 font-medium text-gray-500 hover:text-gray-700',
        align === 'left' ? 'text-left' : 'text-right',
        sticky && 'left-0 z-20 border-r border-gray-100',
      )}
      onClick={onClick}
    >
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
