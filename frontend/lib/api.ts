import type {
  BuyLot, GroupKind, Holding, HoldingDetail, Label, PortfolioScope, PortfolioSummary, PrincipalFlow,
  RollupGroup, ScopedPortfolioHistory, ScopedPortfolioHoldings, SharedGroup, SharedTag,
  SourceGroup, StockSearchResult, Tag, TagDetail, Transaction, User,
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
    principal_flow?: PrincipalFlow
    notes?: string
    source_group_id: string | null
    label_ids: string[]
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
    principal_flow: PrincipalFlow
    source_group_id: string | null
    label_ids: string[]
    sell_allocations: { buy_lot_id: string; quantity: string }[]
  }) =>
    request<Transaction>(`/api/holdings/${holdingId}/transactions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteTransaction: (holdingId: string, txId: string) =>
    request(`/api/holdings/${holdingId}/transactions/${txId}`, { method: 'DELETE' }),

  listLots: (
    holdingId: string,
    scope: { scope_kind: 'source'; scope_id: string } | { scope_kind: 'unclassified' },
  ) => {
    const params = new URLSearchParams({ scope_kind: scope.scope_kind })
    if (scope.scope_kind === 'source') params.set('scope_id', scope.scope_id)
    return request<BuyLot[]>(`/api/holdings/${holdingId}/lots?${params}`)
  },

  listReviewLots: (
    holdingId: string,
    txId: string,
    scope: { scope_kind: 'source'; scope_id: string } | { scope_kind: 'unclassified' },
  ) => {
    const params = new URLSearchParams({ scope_kind: scope.scope_kind })
    if (scope.scope_kind === 'source') params.set('scope_id', scope.scope_id)
    return request<BuyLot[]>(`/api/holdings/${holdingId}/transactions/${txId}/review-lots?${params}`)
  },

  repairReviewedSell: (
    holdingId: string,
    txId: string,
    data: {
      source_group_id: string | null
      label_ids: string[]
      sell_allocations: { buy_lot_id: string; quantity: string }[]
    },
  ) =>
    request<Transaction>(`/api/holdings/${holdingId}/transactions/${txId}/review`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  updateTransactionClassification: (
    holdingId: string,
    txId: string,
    data: { source_group_id: string | null; label_ids: string[] },
  ) =>
    request<Transaction>(`/api/holdings/${holdingId}/transactions/${txId}/classification`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
}

// ── Groups ───────────────────────────────────────────────────────────────────
export const groupsApi = {
  listSources: () => request<SourceGroup[]>('/api/groups/sources'),

  listRollups: () => request<RollupGroup[]>('/api/groups/rollups'),

  listLabels: () => request<Label[]>('/api/groups/labels'),

  create: (
    kind: GroupKind,
    data: { name: string; color?: string; description?: string; source_group_ids?: string[] },
  ) => request<SourceGroup | RollupGroup | Label>(`/api/groups/${kind}`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (
    kind: GroupKind,
    id: string,
    data: { name?: string; color?: string; description?: string; source_group_ids?: string[] },
  ) => request<SourceGroup | RollupGroup | Label>(`/api/groups/${kind}/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (kind: GroupKind, id: string) =>
    request(`/api/groups/${kind}/${id}`, { method: 'DELETE' }),

  enableShare: (kind: GroupKind, id: string, requiresAuth: boolean) =>
    request<SourceGroup | RollupGroup | Label>(`/api/groups/${kind}/${id}/share`, {
      method: 'POST',
      body: JSON.stringify({ requires_auth: requiresAuth }),
    }),

  disableShare: (kind: GroupKind, id: string) =>
    request(`/api/groups/${kind}/${id}/share`, { method: 'DELETE' }),
}

// ── Scoped portfolio ─────────────────────────────────────────────────────────
export function portfolioScopeQuery(scope: PortfolioScope) {
  const params = new URLSearchParams({ scope_kind: scope.kind })
  if ('id' in scope) params.set('scope_id', scope.id)
  return params.toString()
}

function portfolioPath(resource: 'summary' | 'holdings' | 'history', scope: PortfolioScope) {
  return `/api/portfolio/${resource}?${portfolioScopeQuery(scope)}`
}

export const portfolioApi = {
  summaryPath: (scope: PortfolioScope) => portfolioPath('summary', scope),
  holdingsPath: (scope: PortfolioScope) => portfolioPath('holdings', scope),
  historyPath: (scope: PortfolioScope) => portfolioPath('history', scope),
  summary: (scope: PortfolioScope) => request<PortfolioSummary>(portfolioPath('summary', scope)),
  holdings: (scope: PortfolioScope) => request<ScopedPortfolioHoldings>(portfolioPath('holdings', scope)),
  history: (scope: PortfolioScope) => request<ScopedPortfolioHistory>(portfolioPath('history', scope)),
}

// ── Stocks ───────────────────────────────────────────────────────────────────
export const stocksApi = {
  search: (query: string) =>
    request<StockSearchResult[]>(`/api/stocks/search?q=${encodeURIComponent(query)}`),
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
  getGroup: (token: string) => request<SharedGroup>(`/api/groups/share/${token}`),
  getLegacy: (token: string) => request<SharedTag>(`/api/share/${token}`),
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
