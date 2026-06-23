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
type SortKey = 'name' | 'group' | 'quantity' | 'avgPrice' | 'costBasis' | 'currentPrice' | 'currentValueChange' | 'currentValue' | 'profit' | 'profitPct'
type SortDir = 'asc' | 'desc'

const holdingNameColumnClass = 'w-[9rem] min-w-[9rem] max-w-[9rem] px-3 sm:w-[12rem] sm:min-w-[12rem] sm:max-w-[12rem] sm:px-4'

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
  costBasis: string | null
  currentPrice: string | null
  currentValueChange: string | null
  currentValue: string | null
  profit: string | null
  profitPct: number | null
  groups: DashboardHoldingGroupBadge[]
  groupSortText: string
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
      costBasis: holding.remaining_cost_basis,
      currentPrice: holding.current_price,
      currentValueChange: holding.current_value_change ?? null,
      currentValue: holding.current_value,
      profit,
      profitPct: profit === null || cost === null || cost <= 0 ? null : parseFloat(profit) / cost * 100,
      groups: holding.groups,
      groupSortText: holding.groups.map((group) => group.name).join(', '),
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
      costBasis: holding.remaining_cost_basis,
      currentPrice: holding.current_price,
      currentValueChange: null,
      currentValue: holding.current_value,
      profit,
      profitPct: profit === null || cost === null || cost <= 0 ? null : parseFloat(profit) / cost * 100,
      groups: [],
      groupSortText: '',
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
    costBasis: holding.cost_basis,
    currentPrice: holding.current_price,
    currentValueChange: null,
    currentValue: holding.current_value,
    profit: holding.profit_loss,
    profitPct: holding.profit_loss_pct === null ? null : parseFloat(holding.profit_loss_pct),
    groups: [],
    groupSortText: '',
  }
}

const initialSortDir: Record<SortKey, SortDir> = {
  name: 'asc',
  group: 'asc',
  quantity: 'asc',
  avgPrice: 'asc',
  costBasis: 'asc',
  currentPrice: 'asc',
  currentValueChange: 'desc',
  currentValue: 'desc',
  profit: 'desc',
  profitPct: 'desc',
}

export function HoldingsTable({ holdings, displayCurrency }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('profitPct')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((direction) => direction === 'asc' ? 'desc' : 'asc')
    else {
      setSortKey(key)
      setSortDir(initialSortDir[key])
    }
  }

  const rows = holdings.map((holding) => toRow(holding, displayCurrency))
  const total = buildTotalRow(rows, displayCurrency)
  const sorted = [...rows].sort((a, b) => {
    if (sortKey === 'name') return compareText(a.name, b.name, sortDir)
    if (sortKey === 'group') return compareText(a.groupSortText, b.groupSortText, sortDir)
    const left = numericSortValue(a, sortKey)
    const right = numericSortValue(b, sortKey)
    return compareNullableNumber(left, right, sortDir)
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
      <table className="min-w-[1220px] text-sm">
        <thead>
            <tr className="border-b border-gray-100">
            <SortableHeading label="종목" align="left" sticky onClick={() => toggleSort('name')}><SortIcon column="name" /></SortableHeading>
            <SortableHeading label="그룹" align="left" onClick={() => toggleSort('group')}><SortIcon column="group" /></SortableHeading>
            <SortableHeading label="수량" onClick={() => toggleSort('quantity')}><SortIcon column="quantity" /></SortableHeading>
            <SortableHeading label="평균매수가" onClick={() => toggleSort('avgPrice')}><SortIcon column="avgPrice" /></SortableHeading>
            <SortableHeading label="원금" onClick={() => toggleSort('costBasis')}><SortIcon column="costBasis" /></SortableHeading>
            <SortableHeading label="현재가" onClick={() => toggleSort('currentPrice')}><SortIcon column="currentPrice" /></SortableHeading>
            <SortableHeading label="당일손익" onClick={() => toggleSort('currentValueChange')}><SortIcon column="currentValueChange" /></SortableHeading>
            <SortableHeading label="평가금액" onClick={() => toggleSort('currentValue')}><SortIcon column="currentValue" /></SortableHeading>
            <SortableHeading label="평가손익" onClick={() => toggleSort('profit')}><SortIcon column="profit" /></SortableHeading>
            <SortableHeading label="평가손익률" onClick={() => toggleSort('profitPct')}><SortIcon column="profitPct" /></SortableHeading>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {sorted.map((row) => (
            <tr key={row.key} className="group/row transition-colors hover:bg-gray-50">
              <td className={cn('sticky left-0 z-10 border-r border-gray-100 bg-white py-3 group-hover/row:bg-gray-50', holdingNameColumnClass)}>
                {row.id ? <HoldingName row={row} linked /> : <HoldingName row={row} />}
              </td>
              <td className="px-4 py-3"><GroupBadges groups={row.groups} /></td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{formatShareQuantity(row.quantity)}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{formatCurrency(row.avgPrice, row.valueCurrency)}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{row.costBasis ? formatCurrency(row.costBasis, row.valueCurrency) : '—'}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{row.currentPrice ? formatCurrency(row.currentPrice, row.priceCurrency) : '—'}</td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(row.currentValueChange))}>{formatSignedCurrency(row.currentValueChange, row.valueCurrency)}</td>
              <td className="px-4 py-3 text-right tabular-nums text-gray-700">{row.currentValue ? formatCurrency(row.currentValue, row.valueCurrency) : '—'}</td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(row.profit))}>{row.profit ? formatCurrency(row.profit, row.valueCurrency) : '—'}</td>
              <td className={cn('px-4 py-3 text-right tabular-nums font-medium', profitColor(row.profitPct))}>{formatPercent(row.profitPct)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-gray-200 bg-gray-50 font-semibold text-gray-900">
            <td className={cn('sticky left-0 z-10 border-r border-gray-100 bg-gray-50 py-3', holdingNameColumnClass)}>
              합계
            </td>
            <td className="px-4 py-3 text-gray-400">—</td>
            <td className="px-4 py-3 text-right text-gray-400">—</td>
            <td className="px-4 py-3 text-right text-gray-400">—</td>
            <td className="px-4 py-3 text-right tabular-nums">{formatTotalCurrency(total.costBasis, total)}</td>
            <td className="px-4 py-3 text-right text-gray-400">—</td>
            <td className={cn('px-4 py-3 text-right tabular-nums', profitColor(total.currentValueChange))}>{formatTotalSignedCurrency(total.currentValueChange, total)}</td>
            <td className="px-4 py-3 text-right tabular-nums">{formatTotalCurrency(total.currentValue, total)}</td>
            <td className={cn('px-4 py-3 text-right tabular-nums', profitColor(total.profit))}>{formatTotalCurrency(total.profit, total)}</td>
            <td className={cn('px-4 py-3 text-right tabular-nums', profitColor(total.profitPct))}>{formatPercent(total.profitPct)}</td>
          </tr>
        </tfoot>
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

interface TotalRow {
  currency: Currency
  canSum: boolean
  costBasis: number | null
  currentValueChange: number | null
  currentValue: number | null
  profit: number | null
  profitPct: number | null
}

function buildTotalRow(rows: Row[], displayCurrency?: DisplayCurrency): TotalRow {
  const currency = displayCurrency ?? rows[0]?.valueCurrency ?? 'KRW'
  const canSum = rows.every((row) => row.valueCurrency === currency)
  if (!canSum) {
    return { currency, canSum: false, costBasis: null, currentValueChange: null, currentValue: null, profit: null, profitPct: null }
  }
  const costBasis = sumNullable(rows.map((row) => parseNumeric(row.costBasis)))
  const currentValueChange = sumNullable(rows.map((row) => parseNumeric(row.currentValueChange)))
  const currentValue = sumNullable(rows.map((row) => parseNumeric(row.currentValue)))
  const profit = sumNullable(rows.map((row) => parseNumeric(row.profit)))
  const profitPct = costBasis !== null && profit !== null && costBasis > 0 ? profit / costBasis * 100 : null
  return { currency, canSum, costBasis, currentValueChange, currentValue, profit, profitPct }
}

function sumNullable(values: Array<number | null>) {
  const present = values.filter((value): value is number => value !== null && Number.isFinite(value))
  if (present.length === 0) return null
  return present.reduce((sum, value) => sum + value, 0)
}

function formatSignedCurrency(value: string | null, currency: Currency) {
  const numeric = parseNumeric(value)
  if (numeric === null) return '—'
  return `${numeric > 0 ? '+' : ''}${formatCurrency(numeric, currency)}`
}

function formatTotalCurrency(value: number | null, total: TotalRow) {
  if (!total.canSum || value === null) return '—'
  return formatCurrency(value, total.currency)
}

function formatTotalSignedCurrency(value: number | null, total: TotalRow) {
  if (!total.canSum || value === null) return '—'
  return `${value > 0 ? '+' : ''}${formatCurrency(value, total.currency)}`
}

function numericSortValue(row: Row, key: SortKey) {
  if (key === 'quantity') return parseNumeric(row.quantity)
  if (key === 'avgPrice') return row.avgPrice
  if (key === 'costBasis') return parseNumeric(row.costBasis)
  if (key === 'currentPrice') return parseNumeric(row.currentPrice)
  if (key === 'currentValueChange') return parseNumeric(row.currentValueChange)
  if (key === 'currentValue') return parseNumeric(row.currentValue)
  if (key === 'profit') return parseNumeric(row.profit)
  if (key === 'profitPct') return row.profitPct
  return null
}

function compareText(left: string, right: string, direction: SortDir) {
  const leftMissing = left.trim() === ''
  const rightMissing = right.trim() === ''
  if (leftMissing && rightMissing) return 0
  if (leftMissing) return 1
  if (rightMissing) return -1
  const result = left.localeCompare(right)
  return direction === 'asc' ? result : -result
}

function compareNullableNumber(left: number | null, right: number | null, direction: SortDir) {
  const leftMissing = left === null || !Number.isFinite(left)
  const rightMissing = right === null || !Number.isFinite(right)
  if (leftMissing && rightMissing) return 0
  if (leftMissing) return 1
  if (rightMissing) return -1
  return direction === 'asc' ? left - right : right - left
}

function SortableHeading({ label, align = 'right', sticky = false, onClick, children }: { label: string; align?: 'left' | 'right'; sticky?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <th
      className={cn(
        'sticky top-0 z-10 bg-gray-50 px-4 py-3 font-medium text-gray-500',
        align === 'left' ? 'text-left' : 'text-right',
        sticky && ['left-0 z-20 border-r border-gray-100', holdingNameColumnClass],
      )}
    >
      <button
        type="button"
        onClick={onClick}
        className={cn(
          'inline-flex items-center gap-1 font-medium hover:text-gray-700',
          align === 'right' && 'justify-end',
        )}
      >
        {label} {children}
      </button>
    </th>
  )
}

function HoldingName({ row, linked }: { row: Row; linked?: boolean }) {
  const content = (
    <>
      <span className="truncate font-medium text-gray-900 group-hover:text-brand-600">{row.name}</span>
      <span className="truncate text-xs text-gray-400">{row.subtitle}</span>
    </>
  )
  return linked
    ? <Link href={`/holdings/${row.id}`} className="group flex min-w-0 max-w-full flex-col">{content}</Link>
    : <div className="flex min-w-0 max-w-full flex-col">{content}</div>
}
