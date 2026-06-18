'use client'

export type ChartRange = '1m' | '3m' | '6m' | '1y' | 'all'

export const chartRangeOptions: Array<{ value: ChartRange; label: string }> = [
  { value: '1m', label: '1개월' },
  { value: '3m', label: '3개월' },
  { value: '6m', label: '6개월' },
  { value: '1y', label: '1년' },
  { value: 'all', label: '전체' },
]

const chartRangeMonths: Record<Exclude<ChartRange, 'all'>, number> = {
  '1m': 1,
  '3m': 3,
  '6m': 6,
  '1y': 12,
}

export function filterHistoryRowsByChartRange<T extends { snapshot_date: string }>(rows: T[], range: ChartRange): T[] {
  if (range === 'all' || rows.length === 0) return rows
  const latestDate = rows.reduce((latest, row) => (
    row.snapshot_date > latest ? row.snapshot_date : latest
  ), rows[0].snapshot_date)
  const cutoffDate = subtractMonthsFromIsoDate(latestDate, chartRangeMonths[range])
  return rows.filter((row) => row.snapshot_date >= cutoffDate)
}

function subtractMonthsFromIsoDate(value: string, months: number) {
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  date.setUTCMonth(date.getUTCMonth() - months)
  return date.toISOString().slice(0, 10)
}

export function ChartRangeControl({
  value,
  onChange,
}: {
  value: ChartRange
  onChange: (value: ChartRange) => void
}) {
  return (
    <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1" aria-label="차트 기간">
      {chartRangeOptions.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            className={[
              'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
              active ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900',
            ].join(' ')}
            aria-pressed={active}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
