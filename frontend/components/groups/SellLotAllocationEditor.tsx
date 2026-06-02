import { Input } from '@/components/ui/Input'
import { formatCurrency, formatDate, formatNumber } from '@/lib/utils'
import type { BuyLot, Currency } from '@/lib/types'

interface Props {
  lots: BuyLot[]
  allocations: Record<string, string>
  currency: Currency
  loading?: boolean
  onChange: (lotId: string, quantity: string) => void
}

export function SellLotAllocationEditor({ lots, allocations, currency, loading, onChange }: Props) {
  if (loading) return <p className="text-sm text-gray-400">매수 lot을 불러오는 중입니다.</p>
  if (lots.length === 0) return <p className="text-sm text-gray-500">선택한 출처에 매도 가능한 lot이 없습니다.</p>

  return (
    <div className="w-full rounded-lg border border-gray-200 bg-gray-50 p-3">
      <p className="mb-3 text-sm font-medium text-gray-700">매도할 원 매수 lot 배분</p>
      <div className="flex flex-col gap-3">
        {lots.map((lot) => (
          <div key={lot.id} className="grid gap-2 rounded-lg bg-white p-3 sm:grid-cols-[1fr_8rem] sm:items-end">
            <div>
              <p className="text-sm font-medium text-gray-700">{formatDate(lot.transaction_date)} 매수</p>
              <p className="text-xs text-gray-500">
                잔여 {formatNumber(lot.remaining_quantity, 4)}주 / 단가 {formatCurrency(lot.unit_price, currency)}
              </p>
            </div>
            <Input
              id={`sell-lot-allocation-${lot.id}`}
              label={`${formatDate(lot.transaction_date)} 매수 lot 배분`}
              type="number"
              min="0"
              max={lot.remaining_quantity}
              step="any"
              value={allocations[lot.id] ?? ''}
              onChange={(event) => onChange(lot.id, event.target.value)}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
