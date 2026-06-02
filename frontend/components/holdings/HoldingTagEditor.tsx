'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { fetcher, tagsApi } from '@/lib/api'
import type { Tag } from '@/lib/types'

interface Props {
  holdingId: string
  selectedTagIds: string[]
  onRefresh: () => void | Promise<unknown>
}

export function HoldingTagEditor({ holdingId, selectedTagIds, onRefresh }: Props) {
  const { data: tags, isLoading, mutate } = useSWR<Tag[]>('/api/tags', fetcher)
  const [selectedIds, setSelectedIds] = useState(selectedTagIds)
  const [updatingId, setUpdatingId] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setSelectedIds(selectedTagIds)
  }, [selectedTagIds])

  async function toggleTag(tagId: string) {
    const isSelected = selectedIds.includes(tagId)
    setUpdatingId(tagId)
    setError('')
    try {
      if (isSelected) {
        await tagsApi.removeHolding(tagId, holdingId)
        setSelectedIds((current) => current.filter((id) => id !== tagId))
      } else {
        await tagsApi.addHolding(tagId, holdingId)
        setSelectedIds((current) => [...current, tagId])
      }
      await Promise.all([mutate(), onRefresh()])
    } catch (err) {
      setError(err instanceof Error ? err.message : '그룹을 변경하지 못했습니다.')
    } finally {
      setUpdatingId(null)
    }
  }

  if (isLoading) return <p className="text-sm text-gray-400">그룹을 불러오는 중입니다.</p>

  if (!tags || tags.length === 0) {
    return (
      <p className="text-sm text-gray-500">
        아직 그룹이 없습니다. <LinkToGroups />
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-gray-500">
        그룹을 선택해 추가하세요. 이미 포함된 그룹은 다시 누르면 제거됩니다.
      </p>
      <div className="flex flex-wrap gap-2">
        {tags.map((tag) => {
          const isSelected = selectedIds.includes(tag.id)
          return (
            <Button
              key={tag.id}
              type="button"
              variant="secondary"
              size="sm"
              aria-pressed={isSelected}
              loading={updatingId === tag.id}
              disabled={updatingId !== null}
              className={isSelected ? 'border-brand-500 bg-brand-50' : undefined}
              onClick={() => toggleTag(tag.id)}
            >
              <Badge color={tag.color}>{tag.name}</Badge>
              <span className="text-xs text-gray-500">{isSelected ? '제거' : '추가'}</span>
            </Button>
          )
        })}
      </div>
      {error && <p className="text-sm text-red-500">{error}</p>}
    </div>
  )
}

function LinkToGroups() {
  return (
    <Link href="/tags" className="text-brand-600 hover:underline">
      그룹을 먼저 만들어 보세요.
    </Link>
  )
}
