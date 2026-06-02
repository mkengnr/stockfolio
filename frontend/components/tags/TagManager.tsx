'use client'

import { FormEvent, useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { fetcher, tagsApi } from '@/lib/api'
import type { Tag } from '@/lib/types'

const DEFAULT_COLOR = '#2563eb'

export function TagManager() {
  const { data: tags, isLoading, mutate } = useSWR<Tag[]>('/api/tags', fetcher)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState(DEFAULT_COLOR)
  const [creating, setCreating] = useState(false)
  const [editingTag, setEditingTag] = useState<Tag | null>(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editColor, setEditColor] = useState(DEFAULT_COLOR)
  const [updating, setUpdating] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [error, setError] = useState('')

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedName = name.trim()
    if (!trimmedName) return

    setCreating(true)
    setError('')
    try {
      await tagsApi.create({
        name: trimmedName,
        color,
        ...(description.trim() && { description: description.trim() }),
      })
      setName('')
      setDescription('')
      setColor(DEFAULT_COLOR)
      await mutate()
    } catch (err) {
      setError(err instanceof Error ? err.message : '그룹을 생성하지 못했습니다.')
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(tag: Tag) {
    if (!confirm(`${tag.name} 그룹을 삭제하시겠습니까? 종목은 삭제되지 않습니다.`)) return

    setDeletingId(tag.id)
    setError('')
    try {
      await tagsApi.delete(tag.id)
      await mutate()
    } catch (err) {
      setError(err instanceof Error ? err.message : '그룹을 삭제하지 못했습니다.')
    } finally {
      setDeletingId(null)
    }
  }

  function startEdit(tag: Tag) {
    setEditingTag(tag)
    setEditName(tag.name)
    setEditDescription(tag.description ?? '')
    setEditColor(tag.color)
    setError('')
  }

  function cancelEdit() {
    setEditingTag(null)
    setError('')
  }

  async function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedName = editName.trim()
    if (!editingTag || !trimmedName) return

    setUpdating(true)
    setError('')
    try {
      await tagsApi.update(editingTag.id, {
        name: trimmedName,
        color: editColor,
        description: editDescription.trim(),
      })
      setEditingTag(null)
      await mutate()
    } catch (err) {
      setError(err instanceof Error ? err.message : '그룹을 수정하지 못했습니다.')
    } finally {
      setUpdating(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">그룹 관리</h1>
        <p className="mt-1 text-sm text-gray-500">
          관심 종목을 그룹으로 묶고 그룹별 수익률을 확인하세요.
        </p>
      </div>

      <Card>
        <h2 className="font-semibold text-gray-900">새 그룹 만들기</h2>
        <form className="mt-4 flex flex-col gap-4" onSubmit={handleCreate}>
          <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Input
              label="그룹 이름"
              value={name}
              maxLength={50}
              placeholder="예: 장기 투자"
              onChange={(event) => setName(event.target.value)}
            />
            <Input
              label="설명"
              value={description}
              maxLength={200}
              placeholder="선택 사항"
              onChange={(event) => setDescription(event.target.value)}
            />
            <label className="flex flex-col gap-1 text-sm font-medium text-gray-700">
              색상
              <input
                aria-label="그룹 색상"
                type="color"
                value={color}
                onChange={(event) => setColor(event.target.value)}
                className="h-[38px] w-full min-w-20 cursor-pointer rounded-lg border border-gray-300 bg-white px-1 sm:w-20"
              />
            </label>
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <Button className="self-start" type="submit" loading={creating} disabled={!name.trim()}>
            그룹 생성
          </Button>
        </form>
      </Card>

      {editingTag && (
        <Card>
          <h2 className="font-semibold text-gray-900">그룹 수정</h2>
          <form className="mt-4 flex flex-col gap-4" onSubmit={handleUpdate}>
            <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <Input
                label="그룹 이름 수정"
                value={editName}
                maxLength={50}
                onChange={(event) => setEditName(event.target.value)}
              />
              <Input
                label="설명 수정"
                value={editDescription}
                maxLength={200}
                placeholder="선택 사항"
                onChange={(event) => setEditDescription(event.target.value)}
              />
              <label className="flex flex-col gap-1 text-sm font-medium text-gray-700">
                색상 수정
                <input
                  aria-label="그룹 색상 수정"
                  type="color"
                  value={editColor}
                  onChange={(event) => setEditColor(event.target.value)}
                  className="h-[38px] w-full min-w-20 cursor-pointer rounded-lg border border-gray-300 bg-white px-1 sm:w-20"
                />
              </label>
            </div>
            {error && <p className="text-sm text-red-500">{error}</p>}
            <div className="flex gap-2">
              <Button type="submit" loading={updating} disabled={!editName.trim()}>
                수정 저장
              </Button>
              <Button type="button" variant="secondary" onClick={cancelEdit}>
                취소
              </Button>
            </div>
          </form>
        </Card>
      )}

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">내 그룹</h2>
          {tags && <span className="text-sm text-gray-400">{tags.length}개</span>}
        </div>
        {isLoading ? (
          <p className="py-8 text-center text-sm text-gray-400">그룹을 불러오는 중입니다.</p>
        ) : tags && tags.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {tags.map((tag) => (
              <Card key={tag.id} className="flex flex-col gap-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Badge color={tag.color}>{tag.name}</Badge>
                    <p className="mt-2 text-sm text-gray-500">
                      {tag.description || '설명이 없습니다.'}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-gray-400">{tag.holding_ids.length}종목</span>
                </div>
                <div className="mt-auto flex items-center justify-between gap-2">
                  <Link href={`/tags/${tag.id}`} className="text-sm font-medium text-brand-600 hover:underline">
                    상세 보기 →
                  </Link>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" onClick={() => startEdit(tag)}>
                      수정
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={deletingId === tag.id}
                      onClick={() => handleDelete(tag)}
                      className="text-red-500 hover:bg-red-50"
                    >
                      삭제
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <Card>
            <p className="py-4 text-center text-sm text-gray-400">
              아직 그룹이 없습니다. 첫 그룹을 만들어 보세요.
            </p>
          </Card>
        )}
      </div>
    </div>
  )
}
