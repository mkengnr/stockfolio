import { Badge } from '@/components/ui/Badge'
import type { Label } from '@/lib/types'

interface Props {
  labels: Label[]
  selectedIds: string[]
  onChange: (selectedIds: string[]) => void
}

export function LabelMultiSelect({ labels, selectedIds, onChange }: Props) {
  if (labels.length === 0) return null

  function toggleLabel(id: string) {
    onChange(selectedIds.includes(id) ? selectedIds.filter((labelId) => labelId !== id) : [...selectedIds, id])
  }

  return (
    <div>
      <p className="mb-2 text-sm font-medium text-gray-700">라벨 (선택)</p>
      <div className="flex flex-wrap gap-2">
        {labels.map((label) => (
          <button
            key={label.id}
            type="button"
            aria-pressed={selectedIds.includes(label.id)}
            onClick={() => toggleLabel(label.id)}
            className={`rounded-full transition-all ${
              selectedIds.includes(label.id) ? 'ring-2 ring-brand-500 ring-offset-1' : 'opacity-70 hover:opacity-100'
            }`}
          >
            <Badge color={label.color}>{label.name}</Badge>
          </button>
        ))}
      </div>
    </div>
  )
}
