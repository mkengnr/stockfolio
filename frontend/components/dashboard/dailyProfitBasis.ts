const MARKET_LABELS: Record<string, string> = { KRX: '한국', US: '미국' }
const MARKET_ORDER = ['KRX', 'US']

function orderedMarketEntries<T>(byMarket: Record<string, T> | undefined): Array<[string, T]> {
  const rank = (market: string) => {
    const index = MARKET_ORDER.indexOf(market)
    return index === -1 ? MARKET_ORDER.length : index
  }

  return Object.entries(byMarket ?? {})
    .sort(([left], [right]) => rank(left) - rank(right) || left.localeCompare(right))
}

export function formatDailyProfitBasis(
  priceDates: Record<string, string> | undefined,
  comparisonDates: Record<string, string> | undefined,
  activeByMarket: Record<string, boolean> | undefined,
): string {
  return orderedMarketEntries(priceDates)
    .map(([market, currentDate]) => {
      const label = MARKET_LABELS[market] ?? market
      if (activeByMarket?.[market] === false) return `${label} 당일 시세 없음`

      const comparisonDate = comparisonDates?.[market]
      if (currentDate && comparisonDate) return `${label} ${currentDate} vs ${comparisonDate}`
      if (currentDate) return `${label} ${currentDate} 기준`
      return `${label} 기준 정보 없음`
    })
    .join(' · ')
}
