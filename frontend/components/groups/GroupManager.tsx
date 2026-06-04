'use client'

import { FormEvent, useState } from 'react'
import useSWR from 'swr'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { fetcher, groupsApi } from '@/lib/api'
import type { GroupKind, Label, RollupGroup, SourceGroup } from '@/lib/types'

type Group = SourceGroup | RollupGroup | Label

const DEFAULT_COLOR = '#6366f1'

const sectionLabels: Record<GroupKind, string> = {
  sources: '출처 그룹',
  rollups: '통합 그룹',
  labels: '라벨',
}

export function GroupManager() {
  const sourcesState = useSWR<SourceGroup[]>('/api/groups/sources', fetcher)
  const rollupsState = useSWR<RollupGroup[]>('/api/groups/rollups', fetcher)
  const labelsState = useSWR<Label[]>('/api/groups/labels', fetcher)
  const [kind, setKind] = useState<GroupKind>('sources')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState(DEFAULT_COLOR)
  const [memberIds, setMemberIds] = useState<string[]>([])
  const [editing, setEditing] = useState<{ kind: GroupKind; group: Group } | null>(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editColor, setEditColor] = useState(DEFAULT_COLOR)
  const [editMemberIds, setEditMemberIds] = useState<string[]>([])
  const [creating, setCreating] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [pendingAction, setPendingAction] = useState('')
  const [error, setError] = useState('')

  const sources = sourcesState.data ?? []
  const sections: Array<{ kind: GroupKind; groups: Group[]; loading: boolean; error: unknown; onRetry: () => Promise<unknown> }> = [
    { kind: 'sources', groups: sources, loading: sourcesState.isLoading, error: sourcesState.error, onRetry: sourcesState.mutate },
    { kind: 'rollups', groups: rollupsState.data ?? [], loading: rollupsState.isLoading, error: rollupsState.error, onRetry: rollupsState.mutate },
    { kind: 'labels', groups: labelsState.data ?? [], loading: labelsState.isLoading, error: labelsState.error, onRetry: labelsState.mutate },
  ]

  async function refresh(targetKind: GroupKind) {
    await {
      sources: sourcesState.mutate,
      rollups: rollupsState.mutate,
      labels: labelsState.mutate,
    }[targetKind]()
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    setError('')
    try {
      await groupsApi.create(kind, {
        name: name.trim(),
        color,
        ...(description.trim() && { description: description.trim() }),
        ...(kind === 'rollups' && { source_group_ids: memberIds }),
      })
      setName('')
      setDescription('')
      setColor(DEFAULT_COLOR)
      setMemberIds([])
      await refresh(kind)
    } catch (err) {
      setError(err instanceof Error ? err.message : '그룹을 생성하지 못했습니다.')
    } finally {
      setCreating(false)
    }
  }

  function startEdit(groupKind: GroupKind, group: Group) {
    setEditing({ kind: groupKind, group })
    setEditName(group.name)
    setEditDescription(group.description ?? '')
    setEditColor(group.color)
    setEditMemberIds(groupKind === 'rollups' ? (group as RollupGroup).source_group_ids : [])
    setError('')
  }

  async function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing || !editName.trim()) return
    setUpdating(true)
    setError('')
    try {
      await groupsApi.update(editing.kind, editing.group.id, {
        name: editName.trim(),
        color: editColor,
        description: editDescription.trim(),
        ...(editing.kind === 'rollups' && { source_group_ids: editMemberIds }),
      })
      await refresh(editing.kind)
      setEditing(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '그룹을 수정하지 못했습니다.')
    } finally {
      setUpdating(false)
    }
  }

  async function handleDelete(groupKind: GroupKind, group: Group) {
    if (!window.confirm(`${group.name} 그룹을 삭제하시겠습니까?`)) return
    const action = `delete:${groupKind}:${group.id}`
    setPendingAction(action)
    setError('')
    try {
      await groupsApi.delete(groupKind, group.id)
      await refresh(groupKind)
    } catch (err) {
      setError(err instanceof Error ? err.message : '그룹을 삭제하지 못했습니다.')
    } finally {
      setPendingAction('')
    }
  }

  async function handleEnableShare(groupKind: GroupKind, group: Group, requiresAuth: boolean) {
    const action = `share:${groupKind}:${group.id}`
    setPendingAction(action)
    setError('')
    try {
      await groupsApi.enableShare(groupKind, group.id, requiresAuth)
      await refresh(groupKind)
    } catch (err) {
      setError(err instanceof Error ? err.message : '공유를 설정하지 못했습니다.')
    } finally {
      setPendingAction('')
    }
  }

  async function handleDisableShare(groupKind: GroupKind, group: Group) {
    const action = `share:${groupKind}:${group.id}`
    setPendingAction(action)
    setError('')
    try {
      await groupsApi.disableShare(groupKind, group.id)
      await refresh(groupKind)
    } catch (err) {
      setError(err instanceof Error ? err.message : '공유를 중지하지 못했습니다.')
    } finally {
      setPendingAction('')
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">그룹 관리</h1>
        <p className="mt-1 text-sm text-gray-500">
          자금 출처, 통합 조회 범위, 겹쳐서 붙일 수 있는 라벨을 관리하세요.
        </p>
      </div>

      <Card>
        <h2 className="font-semibold text-gray-900">새 그룹 만들기</h2>
        <form className="mt-4 flex flex-col gap-4" onSubmit={handleCreate}>
          <label className="flex flex-col gap-1 text-sm font-medium text-gray-700">
            그룹 종류
            <select
              aria-label="그룹 종류"
              value={kind}
              onChange={(event) => setKind(event.target.value as GroupKind)}
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
            >
              <option value="sources">출처 그룹</option>
              <option value="rollups">통합 그룹</option>
              <option value="labels">라벨</option>
            </select>
          </label>
          <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Input label="그룹 이름" value={name} maxLength={50} onChange={(event) => setName(event.target.value)} />
            <Input label="설명" value={description} maxLength={200} onChange={(event) => setDescription(event.target.value)} />
            <ColorInput label="그룹 색상" value={color} onChange={setColor} />
          </div>
          {kind === 'rollups' && (
            <MemberSelector sources={sources} selectedIds={memberIds} onChange={setMemberIds} />
          )}
          {error && <p className="text-sm text-red-500">{error}</p>}
          <Button className="self-start" type="submit" loading={creating} disabled={!name.trim()}>
            그룹 생성
          </Button>
        </form>
      </Card>

      {editing && (
        <Card>
          <h2 className="font-semibold text-gray-900">{sectionLabels[editing.kind]} 수정</h2>
          <form className="mt-4 flex flex-col gap-4" onSubmit={handleUpdate}>
            <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <Input label="그룹 이름 수정" value={editName} maxLength={50} onChange={(event) => setEditName(event.target.value)} />
              <Input label="설명 수정" value={editDescription} maxLength={200} onChange={(event) => setEditDescription(event.target.value)} />
              <ColorInput label="그룹 색상 수정" value={editColor} onChange={setEditColor} />
            </div>
            {editing.kind === 'rollups' && (
              <MemberSelector sources={sources} selectedIds={editMemberIds} onChange={setEditMemberIds} />
            )}
            <div className="flex gap-2">
              <Button type="submit" loading={updating} disabled={!editName.trim()}>수정 저장</Button>
              <Button type="button" variant="secondary" onClick={() => setEditing(null)}>취소</Button>
            </div>
          </form>
        </Card>
      )}

      {sections.map((section) => (
        <GroupSection
          key={section.kind}
          {...section}
          pendingAction={pendingAction}
          onEdit={startEdit}
          onDelete={handleDelete}
          onEnableShare={handleEnableShare}
          onDisableShare={handleDisableShare}
        />
      ))}
    </div>
  )
}

function ColorInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="flex flex-col gap-1 text-sm font-medium text-gray-700">
      {label}
      <input
        aria-label={label}
        type="color"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-[38px] w-20 cursor-pointer rounded-lg border border-gray-300 bg-white px-1"
      />
    </label>
  )
}

function MemberSelector({
  sources,
  selectedIds,
  onChange,
}: {
  sources: SourceGroup[]
  selectedIds: string[]
  onChange: (ids: string[]) => void
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium text-gray-700">포함할 출처 그룹</legend>
      <div className="flex flex-wrap gap-3">
        {sources.map((source) => (
          <label key={source.id} className="flex items-center gap-2 text-sm text-gray-600">
            <input
              aria-label={`${source.name} 포함`}
              type="checkbox"
              checked={selectedIds.includes(source.id)}
              onChange={() => onChange(
                selectedIds.includes(source.id)
                  ? selectedIds.filter((id) => id !== source.id)
                  : [...selectedIds, source.id],
              )}
            />
            {source.name}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function GroupSection({
  kind,
  groups,
  loading,
  error,
  onRetry,
  pendingAction,
  onEdit,
  onDelete,
  onEnableShare,
  onDisableShare,
}: {
  kind: GroupKind
  groups: Group[]
  loading: boolean
  error: unknown
  onRetry: () => Promise<unknown>
  pendingAction: string
  onEdit: (kind: GroupKind, group: Group) => void
  onDelete: (kind: GroupKind, group: Group) => void
  onEnableShare: (kind: GroupKind, group: Group, requiresAuth: boolean) => void
  onDisableShare: (kind: GroupKind, group: Group) => void
}) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold text-gray-900">{sectionLabels[kind]}</h2>
        <span className="text-sm text-gray-400">{groups.length}개</span>
      </div>
      {error ? (
        <Card className="flex items-center justify-between gap-3">
          <p className="text-sm text-red-500">{sectionLabels[kind]}을 불러오지 못했습니다.</p>
          <Button variant="secondary" size="sm" onClick={() => void onRetry()} aria-label={`${sectionLabels[kind]} 다시 시도`}>
            다시 시도
          </Button>
        </Card>
      ) : loading ? (
        <p className="py-4 text-sm text-gray-400">그룹을 불러오는 중입니다.</p>
      ) : groups.length === 0 ? (
        <Card><p className="text-sm text-gray-400">등록된 그룹이 없습니다.</p></Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {groups.map((group) => (
            <GroupCard
              key={group.id}
              kind={kind}
              group={group}
              pendingAction={pendingAction}
              onEdit={onEdit}
              onDelete={onDelete}
              onEnableShare={onEnableShare}
              onDisableShare={onDisableShare}
            />
          ))}
        </div>
      )}
    </section>
  )
}

function GroupCard({
  kind,
  group,
  pendingAction,
  onEdit,
  onDelete,
  onEnableShare,
  onDisableShare,
}: {
  kind: GroupKind
  group: Group
  pendingAction: string
  onEdit: (kind: GroupKind, group: Group) => void
  onDelete: (kind: GroupKind, group: Group) => void
  onEnableShare: (kind: GroupKind, group: Group, requiresAuth: boolean) => void
  onDisableShare: (kind: GroupKind, group: Group) => void
}) {
  const [requiresAuth, setRequiresAuth] = useState(group.share_requires_auth)
  const sharePending = pendingAction === `share:${kind}:${group.id}`
  const deletePending = pendingAction === `delete:${kind}:${group.id}`
  const shareUrl = group.share_token && typeof window !== 'undefined'
    ? `${window.location.origin}/share/${group.share_token}`
    : ''

  return (
    <Card className="flex flex-col gap-3">
      <div>
        <Badge color={group.color}>{group.name}</Badge>
        <p className="mt-2 text-sm text-gray-500">{group.description || '설명이 없습니다.'}</p>
        {kind === 'rollups' && (
          <p className="mt-1 text-xs text-gray-400">출처 {(group as RollupGroup).source_group_ids.length}개</p>
        )}
      </div>
      {group.share_token ? (
        <div className="rounded-lg bg-gray-50 p-3 text-xs text-gray-500">
          <p className="break-all">{shareUrl}</p>
          <p className="mt-2 text-gray-400">
            {group.share_requires_auth ? '로그인 필요' : '누구나 접근 가능'}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={() => navigator.clipboard.writeText(shareUrl)} aria-label={`${group.name} 공유 링크 복사`}>
              복사
            </Button>
            <a
              className="inline-flex items-center justify-center rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              href={shareUrl}
              target="_blank"
              rel="noreferrer"
              aria-label={`${group.name} 공유 링크 열기`}
            >
              열기
            </a>
            <Button
              variant="secondary"
              size="sm"
              loading={sharePending}
              onClick={() => onDisableShare(kind, group)}
              aria-label={`${group.name} 공유 중지`}
            >
              공유 중지
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2 rounded-lg bg-gray-50 p-3">
          <label className="flex items-center gap-2 text-xs text-gray-600">
            <input type="checkbox" checked={requiresAuth} onChange={(event) => setRequiresAuth(event.target.checked)} />
            로그인한 사용자만 열기
          </label>
          <Button variant="secondary" size="sm" loading={sharePending} onClick={() => onEnableShare(kind, group, requiresAuth)}>
            공유 링크 만들기
          </Button>
        </div>
      )}
      <div className="mt-auto flex justify-end gap-1">
        <Button variant="ghost" size="sm" aria-label={`${group.name} 수정`} onClick={() => onEdit(kind, group)}>수정</Button>
        <Button
          variant="ghost"
          size="sm"
          aria-label={`${group.name} 삭제`}
          loading={deletePending}
          className="text-red-500 hover:bg-red-50"
          onClick={() => onDelete(kind, group)}
        >
          삭제
        </Button>
      </div>
    </Card>
  )
}
