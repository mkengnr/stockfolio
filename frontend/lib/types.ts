export type Market = 'KRX' | 'US'
export type Currency = 'KRW' | 'USD'
export type TxType = 'BUY' | 'SELL'

export interface User {
  id: string
  email: string
  is_admin: boolean
  created_at: string
}

export interface Transaction {
  id: string
  type: TxType
  quantity: string
  price: string
  transaction_date: string
  created_at: string
}

export interface Snapshot {
  snapshot_date: string
  close_price: string
  total_value: string
}

export interface Holding {
  id: string
  ticker: string
  market: Market
  name: string
  quantity: string
  avg_price: string
  currency: Currency
  first_buy_date: string
  notes: string | null
  is_active: boolean
  created_at: string
  // enriched fields (may be null if price unavailable)
  current_price: string | null
  current_value: string | null
  profit_loss: string | null
  profit_loss_pct: string | null
  cost_basis: string | null
}

export interface HoldingDetail extends Holding {
  transactions: Transaction[]
  snapshots: Snapshot[]
  tags: string[]
}

export interface TagSummary {
  total_cost_basis: string
  total_current_value: string | null
  total_profit_loss: string | null
  total_profit_loss_pct: string | null
  holding_count: number
}

export interface Tag {
  id: string
  name: string
  color: string
  description: string | null
  share_token: string | null
  share_requires_auth: boolean
  holding_ids: string[]
  created_at: string
}

export interface TagDetail extends Tag {
  summary: TagSummary | null
}

export interface ApiError {
  detail: string | { msg: string; type: string }[]
}
