import type {
  Holding, HoldingDetail, Tag, TagDetail, User, Transaction,
} from './types'

const BASE = ''  // rewritten to backend by next.config.ts rewrites

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    const err = new Error(
      typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail),
    ) as Error & { status: number }
    err.status = res.status
    throw err
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// SWR fetcher — throws on non-2xx
export const fetcher = <T>(url: string) => request<T>(url)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  requestOtp: (email: string) =>
    request('/api/auth/request-otp', { method: 'POST', body: JSON.stringify({ email }) }),

  verifyOtp: (email: string, code: string, remember_me: boolean) =>
    request<{ user: User; expires_at: string }>('/api/auth/verify-otp', {
      method: 'POST',
      body: JSON.stringify({ email, code, remember_me }),
    }),

  logout: () => request('/api/auth/logout', { method: 'POST' }),

  me: () => request<User>('/api/auth/me'),
}

// ── Holdings ─────────────────────────────────────────────────────────────────
export const holdingsApi = {
  list: () => request<Holding[]>('/api/holdings'),

  create: (data: {
    ticker: string
    quantity: string
    price: string
    transaction_date: string
    notes?: string
  }) => request<HoldingDetail>('/api/holdings', { method: 'POST', body: JSON.stringify(data) }),

  get: (id: string) => request<HoldingDetail>(`/api/holdings/${id}`),

  update: (id: string, data: { notes?: string; name?: string }) =>
    request<Holding>(`/api/holdings/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  delete: (id: string) => request(`/api/holdings/${id}`, { method: 'DELETE' }),

  addTransaction: (holdingId: string, data: {
    type: 'BUY' | 'SELL'
    quantity: string
    price: string
    transaction_date: string
  }) =>
    request<Transaction>(`/api/holdings/${holdingId}/transactions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteTransaction: (holdingId: string, txId: string) =>
    request(`/api/holdings/${holdingId}/transactions/${txId}`, { method: 'DELETE' }),
}

// ── Tags ─────────────────────────────────────────────────────────────────────
export const tagsApi = {
  list: () => request<Tag[]>('/api/tags'),

  create: (data: { name: string; color?: string; description?: string }) =>
    request<Tag>('/api/tags', { method: 'POST', body: JSON.stringify(data) }),

  get: (id: string) => request<TagDetail>(`/api/tags/${id}`),

  update: (id: string, data: { name?: string; color?: string; description?: string }) =>
    request<Tag>(`/api/tags/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  delete: (id: string) => request(`/api/tags/${id}`, { method: 'DELETE' }),

  addHolding: (tagId: string, holdingId: string) =>
    request(`/api/tags/${tagId}/holdings/${holdingId}`, { method: 'POST' }),

  removeHolding: (tagId: string, holdingId: string) =>
    request(`/api/tags/${tagId}/holdings/${holdingId}`, { method: 'DELETE' }),

  enableShare: (tagId: string, requiresAuth: boolean) =>
    request<Tag>(`/api/tags/${tagId}/share`, {
      method: 'POST',
      body: JSON.stringify({ requires_auth: requiresAuth }),
    }),

  disableShare: (tagId: string) =>
    request(`/api/tags/${tagId}/share`, { method: 'DELETE' }),
}

// ── Share (public) ───────────────────────────────────────────────────────────
export const shareApi = {
  get: (token: string) => request<TagDetail>(`/api/share/${token}`),
}

// ── Admin ─────────────────────────────────────────────────────────────────────
export const adminApi = {
  listUsers: () => request<User[]>('/api/admin/users'),

  createUser: (email: string, is_admin = false) =>
    request<User>('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify({ email, is_admin }),
    }),

  patchUser: (id: string, data: { is_active?: boolean; is_admin?: boolean }) =>
    request<User>(`/api/admin/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
}
