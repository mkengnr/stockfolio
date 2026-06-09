export type Market = 'KRX' | 'US'
export type Currency = 'KRW' | 'USD'
export type TxType = 'BUY' | 'SELL'
export type PrincipalFlow = 'DEPOSIT' | 'REINVEST' | 'WITHDRAW'

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
  total_invested_principal: string | null
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

export interface PublicScopedPortfolioHolding {
  ticker: string
  name: string | null
  currency: Currency
  remaining_quantity: string
  remaining_cost_basis: string
  current_price: string | null
  current_value: string | null
  unrealized_profit_loss: string | null
}

export interface ScopedPortfolioHolding extends PublicScopedPortfolioHolding {
  holding_id: string
}

export interface ScopedPortfolioHoldings {
  holdings: ScopedPortfolioHolding[]
  accounting_status: AccountingStatus
  warnings: string[]
}

export interface ScopedPortfolioHistoryPoint {
  snapshot_date: string
  total_value: string | null
  total_invested_principal: string | null
  total_cost_basis: string | null
  total_profit_loss: string | null
  unavailable_price_count: number
  accounting_status: AccountingStatus
  warnings: string[]
}

export interface ScopedPortfolioHistory {
  series: Record<Currency, ScopedPortfolioHistoryPoint[]>
}

export type DisplayCurrency = 'KRW' | 'USD'
export type DashboardGroupKind = 'source' | 'combined' | 'unclassified'
export type DashboardHistoryGroupKind = 'total' | DashboardGroupKind

export interface DashboardExchangeRate {
  base: string
  quote: string
  rate: string
  as_of: string
}

export interface DashboardSummary {
  total_invested_principal: string | null
  total_cost_basis: string | null
  total_current_value: string | null
  total_current_value_change: string | null
  total_unrealized_profit_loss: string | null
  total_unrealized_profit_loss_pct: string | null
  total_profit_loss: string | null
  total_profit_loss_pct: string | null
}

export interface DashboardGroupSummary {
  kind: DashboardGroupKind
  id: string | null
  name: string
  color: string | null
  source_group_ids: string[]
  summary: DashboardSummary
  holdings: DashboardHoldingRow[]
}

export interface DashboardHoldingGroupBadge {
  source_group_id: string | null
  name: string
  color: string | null
  remaining_quantity: string
}

export interface DashboardHoldingRow {
  holding_id: string
  ticker: string
  name: string | null
  market: Market
  currency: Currency
  quantity: string
  remaining_cost_basis: string | null
  current_price: string | null
  current_value: string | null
  unrealized_profit_loss: string | null
  groups: DashboardHoldingGroupBadge[]
}

export interface DashboardHistoryRow {
  group_kind: DashboardHistoryGroupKind
  group_id: string | null
  group_name: string
  snapshot_date: string
  total_value: string | null
  total_invested_principal: string | null
  total_cost_basis: string | null
  total_profit_loss: string | null
}

export interface DashboardResponse {
  display_currency: DisplayCurrency
  exchange_rate: DashboardExchangeRate | null
  last_refreshed_at: string
  current_price_as_of: string | null
  comparison_as_of: string | null
  summary: DashboardSummary
  groups: DashboardGroupSummary[]
  history: { rows: DashboardHistoryRow[] }
  holdings: DashboardHoldingRow[]
  warnings: string[]
}

export interface Transaction {
  id: string
  type: TxType
  quantity: string
  price: string
  transaction_date: string
  principal_flow: PrincipalFlow
  created_at: string
  source_group_id: string | null
  label_ids: string[]
  requires_review: boolean
  buy_lot: BuyLot | null
  sell_allocations: SellLotAllocation[]
}

export interface TransactionListItem {
  id: string
  holding_id: string
  ticker: string
  holding_name: string
  currency: Currency
  type: TxType
  transaction_date: string
  quantity: string
  price: string
  amount: string
  principal_flow: PrincipalFlow
  source_group_id: string | null
  source_group_name: string | null
  label_ids: string[]
  label_names: string[]
  requires_review: boolean
  created_at: string
}

export interface TransactionListPayload {
  transactions: TransactionListItem[]
}

export interface TransactionFilters {
  date_from?: string
  date_to?: string
  q?: string
  source_group_id?: string
  type?: TxType
  principal_flow?: PrincipalFlow
  requires_review?: 'true' | 'false'
}

export interface TransactionUpdatePayload {
  transaction_date?: string
  quantity?: string
  price?: string
  principal_flow?: PrincipalFlow
  source_group_id?: string | null
  label_ids?: string[]
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

export interface HoldingPerformance {
  total_invested_principal: string
  remaining_cost_basis: string
  current_value: string | null
  profit_loss: string | null
  profit_loss_pct: string | null
}

export interface HoldingGroupBreakdown {
  source_group_id: string | null
  name: string
  color: string | null
  remaining_quantity: string
  invested_principal: string
  remaining_cost_basis: string
  current_value: string | null
  profit_loss: string | null
  profit_loss_pct: string | null
}

export interface HoldingDetail extends Holding {
  transactions: Transaction[]
  snapshots: Snapshot[]
  tags: string[]
  performance: HoldingPerformance | null
  group_breakdown: HoldingGroupBreakdown[]
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
  dashboard: SharedDashboard
}

export interface SharedDashboardHoldingGroupBadge {
  name: string
  color: string | null
  remaining_quantity: string
}

export interface SharedDashboardHolding {
  ticker: string
  name: string | null
  market: Market
  currency: Currency
  quantity: string
  remaining_cost_basis: string | null
  current_price: string | null
  current_value: string | null
  unrealized_profit_loss: string | null
  groups: SharedDashboardHoldingGroupBadge[]
}

export interface SharedDashboardGroup {
  key: string
  kind: 'source'
  name: string
  color: string | null
  summary: DashboardSummary
  holdings: SharedDashboardHolding[]
}

export interface SharedDashboardHistoryRow {
  group_key: string
  group_kind: 'total' | 'source'
  group_name: string
  snapshot_date: string
  total_value: string | null
  total_invested_principal: string | null
  total_cost_basis: string | null
  total_profit_loss: string | null
}

export interface SharedDashboard {
  display_currency: DisplayCurrency
  summary: DashboardSummary
  groups: SharedDashboardGroup[]
  history: { rows: SharedDashboardHistoryRow[] }
  holdings: SharedDashboardHolding[]
}

export interface ApiError {
  detail: string | { msg: string; type: string }[]
}
