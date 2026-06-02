import type { SourceGroup } from '@/lib/types'

interface Props {
  groups: SourceGroup[]
  value: string | null
  onChange: (value: string | null) => void
  id?: string
  label?: string
}

export function SourceGroupSelect({
  groups,
  value,
  onChange,
  id = 'source-group',
  label = '출처 그룹',
}: Props) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-gray-700">
        {label}
      </label>
      <select
        id={id}
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value || null)}
        className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
      >
        <option value="">미분류</option>
        {groups.map((group) => (
          <option key={group.id} value={group.id}>
            {group.name}
          </option>
        ))}
      </select>
    </div>
  )
}
