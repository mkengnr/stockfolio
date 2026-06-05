'use client'

import { cn } from '@/lib/utils'

export type DashboardChartMetric = 'value' | 'principal' | 'profit'
export type DashboardChartView = 'combined' | 'separate'

interface Props {
  metric: DashboardChartMetric
  view: DashboardChartView
  onMetricChange: (metric: DashboardChartMetric) => void
  onViewChange: (view: DashboardChartView) => void
}

const metricLabels: Array<{ value: DashboardChartMetric; label: string }> = [
  { value: 'value', label: '평가금액' },
  { value: 'principal', label: '투자원금' },
  { value: 'profit', label: '총손익' },
]

const viewLabels: Array<{ value: DashboardChartView; label: string }> = [
  { value: 'combined', label: '하나의 차트' },
  { value: 'separate', label: '각각 보기' },
]

export function DashboardChartControls({ metric, view, onMetricChange, onViewChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      <SegmentedControl
        ariaLabel="차트 지표"
        value={metric}
        options={metricLabels}
        onChange={onMetricChange}
      />
      <SegmentedControl
        ariaLabel="차트 보기"
        value={view}
        options={viewLabels}
        onChange={onViewChange}
      />
    </div>
  )
}

function SegmentedControl<T extends string>({
  ariaLabel,
  value,
  options,
  onChange,
}: {
  ariaLabel: string
  value: T
  options: Array<{ value: T; label: string }>
  onChange: (value: T) => void
}) {
  return (
    <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1" aria-label={ariaLabel}>
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            className={cn(
              'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
              active ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900',
            )}
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
