'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'

export interface GroupFilterOption {
  value: string
  label: string
}

interface Props {
  value: string
  options: GroupFilterOption[]
  onChange: (value: string) => void
  className?: string
}

export function GroupFilterMenu({ value, options, onChange, className }: Props) {
  const [open, setOpen] = useState(false)
  const selected = options.find((option) => option.value === value) ?? options[0]

  function select(value: string) {
    onChange(value)
    setOpen(false)
  }

  return (
    <div className={cn('relative min-w-0', className)}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full min-w-0 items-center justify-between gap-3 rounded-lg border border-gray-300 bg-white px-3 py-2 text-left text-sm text-gray-900 shadow-sm transition-colors hover:border-gray-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
      >
        <span className="shrink-0 font-medium text-gray-500">그룹 필터</span>
        <span className="min-w-0 flex-1 truncate text-right font-medium">{selected?.label ?? '전체'}</span>
        <span className="text-xs text-gray-400" aria-hidden>v</span>
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 max-h-72 w-full min-w-56 overflow-auto rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
          <div role="listbox" aria-label="그룹 필터" className="outline-none">
            {options.map((option) => {
              const active = option.value === selected?.value
              return (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => select(option.value)}
                  className={cn(
                    'flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors',
                    active ? 'bg-brand-50 font-medium text-brand-700' : 'text-gray-700 hover:bg-gray-50',
                  )}
                >
                  <span className="truncate">{option.label}</span>
                  {active && <span className="text-xs" aria-hidden>*</span>}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
