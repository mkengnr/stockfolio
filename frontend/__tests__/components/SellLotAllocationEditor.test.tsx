import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { SellLotAllocationEditor } from '@/components/groups/SellLotAllocationEditor'
import type { BuyLot } from '@/lib/types'

const lots: BuyLot[] = [
  {
    id: 'lot-1',
    transaction_id: 'tx-1',
    source_group_id: 'source-1',
    original_quantity: '2',
    remaining_quantity: '2',
    unit_price: '80000',
    transaction_date: '2026-01-01',
  },
  {
    id: 'lot-2',
    transaction_id: 'tx-2',
    source_group_id: 'source-1',
    original_quantity: '1',
    remaining_quantity: '0.5',
    unit_price: '90000',
    transaction_date: '2026-02-01',
  },
]

describe('SellLotAllocationEditor', () => {
  it('shows the loading message while lots load', () => {
    render(
      <SellLotAllocationEditor lots={[]} allocations={{}} currency="KRW" loading onChange={jest.fn()} />,
    )

    expect(screen.getByText('매수 lot을 불러오는 중입니다.')).toBeInTheDocument()
  })

  it('shows an empty state when the source has no sellable lots', () => {
    render(
      <SellLotAllocationEditor lots={[]} allocations={{}} currency="KRW" onChange={jest.fn()} />,
    )

    expect(screen.getByText('선택한 출처에 매도 가능한 lot이 없습니다.')).toBeInTheDocument()
  })

  it('renders one allocation input per lot capped at its remaining quantity', () => {
    render(
      <SellLotAllocationEditor
        lots={lots}
        allocations={{ 'lot-1': '1' }}
        currency="KRW"
        onChange={jest.fn()}
      />,
    )

    const first = screen.getByLabelText('2026. 01. 01. 매수 lot 배분') as HTMLInputElement
    const second = screen.getByLabelText('2026. 02. 01. 매수 lot 배분') as HTMLInputElement
    expect(first.value).toBe('1')
    expect(first.max).toBe('2')
    expect(second.value).toBe('')
    expect(second.max).toBe('0.5')
  })

  it('propagates allocation edits with the lot id', () => {
    const onChange = jest.fn()
    render(
      <SellLotAllocationEditor lots={lots} allocations={{}} currency="KRW" onChange={onChange} />,
    )

    fireEvent.change(screen.getByLabelText('2026. 01. 01. 매수 lot 배분'), { target: { value: '1.5' } })

    expect(onChange).toHaveBeenCalledWith('lot-1', '1.5')
  })
})
