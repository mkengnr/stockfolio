const SCALE = 6
const UNIT = BigInt('1000000')
const MAX_INTEGER_DIGITS = 20 - SCALE

export function toFixedDecimalUnits(value: string): bigint | null {
  const match = value.trim().match(/^(\d+)(?:\.(\d+))?$/)
  if (!match) return null

  const integer = match[1].replace(/^0+(?=\d)/, '')
  const fraction = match[2] ?? ''
  if (integer.length > MAX_INTEGER_DIGITS || fraction.length > SCALE) return null

  return BigInt(integer) * UNIT + BigInt(fraction.padEnd(SCALE, '0'))
}

export function isPositiveFixedDecimal(value: string): boolean {
  const units = toFixedDecimalUnits(value)
  return units !== null && units > BigInt(0)
}

export function compareFixedDecimals(left: string, right: string): number | null {
  const leftUnits = toFixedDecimalUnits(left)
  const rightUnits = toFixedDecimalUnits(right)
  if (leftUnits === null || rightUnits === null) return null
  if (leftUnits === rightUnits) return 0
  return leftUnits > rightUnits ? 1 : -1
}

export function sumFixedDecimals(values: string[]): string | null {
  let sum = BigInt(0)
  for (const value of values) {
    const units = toFixedDecimalUnits(value)
    if (units === null) return null
    sum += units
  }
  return formatFixedDecimalUnits(sum)
}

function formatFixedDecimalUnits(units: bigint): string {
  const integer = units / UNIT
  const fraction = String(units % UNIT).padStart(SCALE, '0').replace(/0+$/, '')
  return fraction ? `${integer}.${fraction}` : String(integer)
}
