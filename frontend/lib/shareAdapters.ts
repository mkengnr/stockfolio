import type {
  DashboardHistoryRow,
  DashboardHoldingRow,
  SharedDashboardHistoryRow,
  SharedDashboardHolding,
} from '@/lib/types'

export function toDashboardHistoryRow(row: SharedDashboardHistoryRow): DashboardHistoryRow {
  return {
    group_kind: row.group_kind,
    group_id: row.group_key === 'total' ? null : row.group_key,
    group_name: row.group_name,
    snapshot_date: row.snapshot_date,
    total_value: row.total_value,
    total_invested_principal: row.total_invested_principal,
    total_cost_basis: row.total_cost_basis,
    total_profit_loss: row.total_profit_loss,
  }
}

export function toDashboardHolding(holding: SharedDashboardHolding): DashboardHoldingRow {
  return {
    holding_id: null,
    ticker: holding.ticker,
    name: holding.name,
    market: holding.market,
    currency: holding.currency,
    quantity: holding.quantity,
    remaining_cost_basis: holding.remaining_cost_basis,
    current_price: holding.current_price,
    current_value: holding.current_value,
    unrealized_profit_loss: holding.unrealized_profit_loss,
    groups: holding.groups.map((badge) => ({ ...badge, source_group_id: null })),
  }
}
