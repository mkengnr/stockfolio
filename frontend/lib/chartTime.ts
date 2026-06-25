export function toIsoDateKey(time: unknown): string | null {
  if (typeof time === 'string') return time
  if (
    time !== null
    && typeof time === 'object'
    && 'year' in time
    && 'month' in time
    && 'day' in time
  ) {
    const { year, month, day } = time as { year: number; month: number; day: number }
    return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  }
  return null
}
