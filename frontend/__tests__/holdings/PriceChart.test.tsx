import '@testing-library/jest-dom'
import { StrictMode } from 'react'
import { render, waitFor } from '@testing-library/react'
import {
  PriceChart,
  buildPricePoints,
  buildTransactionMarkers,
  buildPriceTooltipData,
} from '@/components/holdings/PriceChart'
import type { Snapshot, Transaction } from '@/lib/types'

const remove = jest.fn()
const applyOptions = jest.fn()
const fitContent = jest.fn()
const setData = jest.fn()
const setMarkers = jest.fn()
const subscribeCrosshairMove = jest.fn()
const unsubscribeCrosshairMove = jest.fn()
const createChart = jest.fn(() => ({
  addAreaSeries: jest.fn(() => ({ setData, setMarkers })),
  timeScale: jest.fn(() => ({ fitContent })),
  subscribeCrosshairMove,
  unsubscribeCrosshairMove,
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
] as unknown as Snapshot[]

const priceSnaps: Snapshot[] = [
  { snapshot_date: '2026-06-01', close_price: '100', total_value: '0' },
  { snapshot_date: '2026-06-02', close_price: '110', total_value: '0' },
]

const tx = (over: Partial<Transaction>): Transaction => ({
  id: 't', type: 'BUY', quantity: '10', price: '100',
  transaction_date: '2026-06-01', principal_flow: 'IN',
  created_at: '2026-06-01T00:00:00Z', source_group_id: null,
  label_ids: [], requires_review: false, buy_lot: null, sell_allocations: [],
  ...over,
})

describe('buildPricePoints', () => {
  it('appends today + current price when today is after the last snapshot', () => {
    expect(buildPricePoints(priceSnaps, '120', '2026-06-03')).toEqual([
      { time: '2026-06-01', value: 100 },
      { time: '2026-06-02', value: 110 },
      { time: '2026-06-03', value: 120 },
    ])
  })

  it('overrides the last point value when today equals the last snapshot', () => {
    expect(buildPricePoints(priceSnaps, '115', '2026-06-02')).toEqual([
      { time: '2026-06-01', value: 100 },
      { time: '2026-06-02', value: 115 },
    ])
  })

  it('leaves points unchanged when current price is null or not numeric', () => {
    expect(buildPricePoints(priceSnaps, null, '2026-06-03')).toEqual([
      { time: '2026-06-01', value: 100 },
      { time: '2026-06-02', value: 110 },
    ])
  })

  it('returns empty for empty snapshots', () => {
    expect(buildPricePoints([], '120', '2026-06-03')).toEqual([])
  })
})

describe('buildTransactionMarkers', () => {
  it('maps buy/sell to Korean-colored arrows with quantity labels, sorted by date', () => {
    const markers = buildTransactionMarkers([
      tx({ type: 'SELL', quantity: '5', transaction_date: '2026-06-03' }),
      tx({ type: 'BUY', quantity: '10', transaction_date: '2026-06-01' }),
    ], { from: '2026-06-01', to: '2026-06-03' })
    expect(markers).toEqual([
      { time: '2026-06-01', position: 'belowBar', shape: 'arrowUp', color: '#dc2626', text: '매수 10' },
      { time: '2026-06-03', position: 'aboveBar', shape: 'arrowDown', color: '#2563eb', text: '매도 5' },
    ])
  })

  it('drops trailing zeros in quantity and excludes out-of-range dates', () => {
    const markers = buildTransactionMarkers([
      tx({ quantity: '0.500', transaction_date: '2026-06-02' }),
      tx({ quantity: '10', transaction_date: '2026-05-01' }),
    ], { from: '2026-06-01', to: '2026-06-03' })
    expect(markers).toEqual([
      { time: '2026-06-02', position: 'belowBar', shape: 'arrowUp', color: '#dc2626', text: '매수 0.5' },
    ])
  })
})

describe('buildPriceTooltipData', () => {
  it('maps each date to its price and same-day transactions', () => {
    const map = buildPriceTooltipData(
      priceSnaps,
      [tx({ type: 'BUY', quantity: '10', price: '100', transaction_date: '2026-06-01' })],
      '120',
      '2026-06-03',
    )
    expect(map.get('2026-06-01')).toEqual({
      date: '2026-06-01', price: 100,
      txs: [{ type: 'BUY', quantity: '10', price: '100' }],
    })
    expect(map.get('2026-06-03')).toEqual({ date: '2026-06-03', price: 120, txs: [] })
  })

  it('includes transaction-only dates with a null price', () => {
    const map = buildPriceTooltipData(
      priceSnaps,
      [tx({ type: 'SELL', quantity: '2', price: '130', transaction_date: '2026-05-20' })],
      null,
      '2026-06-03',
    )
    expect(map.get('2026-05-20')).toEqual({
      date: '2026-05-20', price: null,
      txs: [{ type: 'SELL', quantity: '2', price: '130' }],
    })
  })
})

describe('PriceChart', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('creates only one chart instance in React StrictMode', async () => {
    render(
      <StrictMode>
        <PriceChart snapshots={snapshots} currency="KRW" currentPrice={null} transactions={[]} />
      </StrictMode>,
    )

    await waitFor(() => expect(createChart).toHaveBeenCalledTimes(1))
    expect(setData).toHaveBeenCalledWith([{ time: '2026-06-01', value: 105 }])
  })

  it('configures ISO dates, draws markers, and subscribes the crosshair with cleanup', async () => {
    const { unmount } = render(
      <PriceChart
        snapshots={snapshots}
        currency="KRW"
        currentPrice={null}
        transactions={[tx({ type: 'BUY', quantity: '10', transaction_date: '2026-06-01' })]}
      />,
    )

    await waitFor(() => expect(createChart).toHaveBeenCalledTimes(1))
    expect(createChart.mock.calls[0][0].localization.dateFormat).toBe('yyyy-MM-dd')
    expect(setMarkers).toHaveBeenCalledWith([
      { time: '2026-06-01', position: 'belowBar', shape: 'arrowUp', color: '#dc2626', text: '매수 10' },
    ])
    await waitFor(() => expect(subscribeCrosshairMove).toHaveBeenCalledTimes(1))
    const handler = subscribeCrosshairMove.mock.calls[0][0]
    unmount()
    expect(unsubscribeCrosshairMove).toHaveBeenCalledWith(handler)
  })
})
