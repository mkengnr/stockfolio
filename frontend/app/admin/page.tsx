'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { fetcher, adminApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import type { User } from '@/lib/types'

function AdminContent() {
  const { data: users, isLoading, mutate } = useSWR<User[]>('/api/admin/users', fetcher)
  const [email, setEmail] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [addLoading, setAddLoading] = useState(false)
  const [addError, setAddError] = useState('')

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setAddError('')
    setAddLoading(true)
    try {
      await adminApi.createUser(email, isAdmin)
      setEmail('')
      setIsAdmin(false)
      mutate()
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : '등록 오류')
    } finally {
      setAddLoading(false)
    }
  }

  async function toggleActive(user: User) {
    await adminApi.patchUser(user.id, { is_active: !user.is_active })
    mutate()
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-gray-900">관리자</h1>

      {/* Add user */}
      <Card>
        <h2 className="mb-4 font-medium text-gray-900">이메일 등록</h2>
        <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-3">
          <Input
            label="이메일"
            type="email"
            placeholder="user@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-64"
          />
          <label className="flex items-center gap-2 text-sm text-gray-600 pb-2">
            <input
              type="checkbox"
              checked={isAdmin}
              onChange={(e) => setIsAdmin(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300"
            />
            관리자
          </label>
          <Button type="submit" loading={addLoading}>등록</Button>
          {addError && <p className="w-full text-sm text-red-500">{addError}</p>}
        </form>
      </Card>

      {/* User list */}
      <Card noPad>
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="font-medium text-gray-900">사용자 목록</h2>
        </div>
        {isLoading ? (
          <p className="px-6 py-4 text-sm text-gray-400">로딩 중...</p>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="border-b border-gray-100 bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left font-medium text-gray-500">이메일</th>
                <th className="px-6 py-3 text-left font-medium text-gray-500">권한</th>
                <th className="px-6 py-3 text-left font-medium text-gray-500">가입일</th>
                <th className="px-6 py-3 text-left font-medium text-gray-500">상태</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {(users ?? []).map((u) => (
                <tr key={u.id} className="hover:bg-gray-50">
                  <td className="px-6 py-3 text-gray-900">{u.email}</td>
                  <td className="px-6 py-3">
                    <span className={`text-xs font-medium ${u.is_admin ? 'text-brand-600' : 'text-gray-400'}`}>
                      {u.is_admin ? '관리자' : '일반'}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-gray-500">{formatDate(u.created_at)}</td>
                  <td className="px-6 py-3">
                    <span className={`text-xs font-medium ${u.is_active ? 'text-green-600' : 'text-red-400'}`}>
                      {u.is_active ? '활성' : '비활성'}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleActive(u)}
                    >
                      {u.is_active ? '비활성화' : '활성화'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}

export default function AdminPage() {
  return (
    <AuthGuard adminOnly>
      <AdminContent />
    </AuthGuard>
  )
}
