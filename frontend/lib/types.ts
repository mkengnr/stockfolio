export type Market = 'KRX' | 'US'
export type Currency = 'KRW' | 'USD'
export type TxType = 'BUY' | 'SELL'

export interface GroupMetadata {
  id: string
  name: string
  color: string
  description: string | null
  share_token: string | null
  share_requires_auth: boolean
  created_at: string
}

export type SourceGroup = GroupMetadata

export type Label = GroupMetadata

export interface RollupGroup extends GroupMetadata {
  source_group_ids: string[]
}

export type GroupKind = 'sources' | 'rollups' | 'labels'

export type PortfolioScope =
  | { kind: 'all' }
  | { kind: 'unclassified' }
  | { kind: 'source'; id: string }
  | { kind: 'rollup'; id: string }
  | { kind: 'label'; id: string }

export interface User {
  id: string
  email: string
  is_admin: boolean
  is_active: boolean
  created_at: string
}

export interface StockSearchResult {
  ticker: string
  name: string
  market: Market
  currency: Currency
}

export interface PortfolioHistoryPoint {
  snapshot_date: string
  total_value: string
  total_cost_basis: string
}

export interface PortfolioHistory {
  series: Record<Currency, PortfolioHistoryPoint[]>
}

export type AccountingStatus = 'ok' | 'requires_review'

export interface PortfolioCurrencySummary {
  total_cost_basis: string | null
  total_current_value: string | null
  total_profit_loss: string | null
  total_profit_loss_pct: string | null
  holding_count: number
}

export interface PortfolioSummary {
  currencies: Partial<Record<Currency, PortfolioCurrencySummary>>
  holding_count: number
  accounting_status: AccountingStatus
  warnings: string[]
}

export interface ScopedPortfolioHolding {
  ticker: string
  name: string | null
  currency: Currency
  remaining_quantity: string
  remaining_cost_basis: string
  current_price: string | null
  current_value: string | null
  unrealized_profit_loss: string | null
}

export interface ScopedPortfolioHoldings {
  holdings: ScopedPortfolioHolding[]
  accounting_status: AccountingStatus
  warnings: string[]
}

export interface ScopedPortfolioHistoryPoint {
  snapshot_date: string
  total_value: string | null
  total_cost_basis: string | null
  total_profit_loss: string | null
  unavailable_price_count: number
  accounting_status: AccountingStatus
  warnings: string[]
}

export interface ScopedPortfolioHistory {
  series: Record<Currency, ScopedPortfolioHistoryPoint[]>
}

export interface Transaction {
  id: string
  type: TxType
  quantity: string
  price: string
  transaction_date: string
  created_at: string
  source_group_id: string | null
  label_ids: string[]
  requires_review: boolean
  buy_lot: BuyLot | null
  sell_allocations: SellLotAllocation[]
}

export interface BuyLot {
  id: string
  transaction_id: string
  source_group_id: string | null
  label_ids: string[]
  original_quantity: string
  remaining_quantity: string
  unit_price: string
  transaction_date: string
}

export interface SellLotAllocation {
  buy_lot_id: string
  quantity: string
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

export interface TagCurrencySummary {
  total_cost_basis: string
  total_current_value: string | null
  total_profit_loss: string | null
  total_profit_loss_pct: string | null
  holding_count: number
}

export interface TagSummary {
  currencies: Partial<Record<Currency, TagCurrencySummary>>
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

export interface SharedTag {
  name: string
  color: string
  description: string | null
  summary: TagSummary | null
  holding_count: number
}

export interface SharedGroup {
  kind: 'source' | 'rollup' | 'label'
  name: string
  color: string
  description: string | null
  summary: PortfolioSummary
  holdings: ScopedPortfolioHoldings
  history: ScopedPortfolioHistory
}

export interface ApiError {
  detail: string | { msg: string; type: string }[]
}
