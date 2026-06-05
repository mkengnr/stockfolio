import '@testing-library/jest-dom'
import { StrictMode } from 'react'
import { render, waitFor } from '@testing-library/react'
import { PriceChart } from '@/components/holdings/PriceChart'

const remove = jest.fn()
const applyOptions = jest.fn()
const fitContent = jest.fn()
const setData = jest.fn()
const createChart = jest.fn(() => ({
  addAreaSeries: jest.fn(() => ({ setData })),
  timeScale: jest.fn(() => ({ fitContent })),
  applyOptions,
  remove,
}))

jest.mock('lightweight-charts', () => ({
  createChart,
  ColorType: { Solid: 'solid' },
}))

const snapshots = [
  {
    id: 'snapshot-1',
    snapshot_date: '2026-06-01',
    open_price: '100',
    high_price: '110',
    low_price: '95',
    close_price: '105',
    volume: '1000',
    source: 'test',
  },
]

describe('PriceChart', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('creates only one chart instance in React StrictMode', async () => {
    render(
      <StrictMode>
        <PriceChart snapshots={snapshots} currency="KRW" />
      </StrictMode>,
    )

    await waitFor(() => expect(createChart).toHaveBeenCalledTimes(1))
    expect(setData).toHaveBeenCalledWith([{ time: '2026-06-01', value: 105 }])
  })
})
