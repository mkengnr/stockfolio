import type { Label, PortfolioScope, RollupGroup, SourceGroup } from '@/lib/types'
export { portfolioScopeQuery } from '@/lib/api'

interface Props {
  value: PortfolioScope
  sources: SourceGroup[]
  rollups: RollupGroup[]
  labels: Label[]
  onChange: (scope: PortfolioScope) => void
}

function scopeValue(scope: PortfolioScope): string {
  return 'id' in scope ? `${scope.kind}:${scope.id}` : scope.kind
}

function parseScope(value: string): PortfolioScope {
  if (value === 'all' || value === 'unclassified') return { kind: value }
  const [kind, id] = value.split(':', 2)
  return { kind: kind as 'source' | 'rollup' | 'label', id }
}

export function ScopeFilter({ value, sources, rollups, labels, onChange }: Props) {
  return (
    <label className="flex items-center gap-2 text-sm text-gray-600">
      <span className="shrink-0 font-medium">조회 범위</span>
      <select
        aria-label="대시보드 범위"
        value={scopeValue(value)}
        onChange={(event) => onChange(parseScope(event.target.value))}
        className="min-w-48 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
      >
        <option value="all">전체 포트폴리오</option>
        <option value="unclassified">미분류</option>
        {sources.map((group) => (
          <option key={group.id} value={`source:${group.id}`}>출처: {group.name}</option>
        ))}
        {rollups.map((group) => (
          <option key={group.id} value={`rollup:${group.id}`}>통합: {group.name}</option>
        ))}
        {labels.map((label) => (
          <option key={label.id} value={`label:${label.id}`}>라벨: {label.name}</option>
        ))}
      </select>
    </label>
  )
}
