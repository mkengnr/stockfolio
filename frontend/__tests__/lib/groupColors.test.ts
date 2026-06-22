import { GROUP_COLOR_PRESETS, recommendGroupColor } from '@/lib/groupColors'

describe('recommendGroupColor', () => {
  const first = GROUP_COLOR_PRESETS[0].value

  it('returns the first preset when nothing is used', () => {
    expect(recommendGroupColor([])).toBe(first)
  })

  it('skips used presets and returns the first unused one', () => {
    const used = [GROUP_COLOR_PRESETS[0].value, GROUP_COLOR_PRESETS[1].value]
    expect(recommendGroupColor(used)).toBe(GROUP_COLOR_PRESETS[2].value)
  })

  it('normalizes case when comparing used colors', () => {
    const used = [GROUP_COLOR_PRESETS[0].value.toUpperCase()]
    expect(recommendGroupColor(used)).toBe(GROUP_COLOR_PRESETS[1].value)
  })

  it('falls back to the first preset when every preset is used', () => {
    const used = GROUP_COLOR_PRESETS.map((preset) => preset.value)
    expect(recommendGroupColor(used)).toBe(first)
  })

  it('exposes twelve distinct presets', () => {
    const values = GROUP_COLOR_PRESETS.map((preset) => preset.value.toLowerCase())
    expect(values).toHaveLength(12)
    expect(new Set(values).size).toBe(12)
  })

  it('includes a readable yellow preset', () => {
    expect(GROUP_COLOR_PRESETS).toContainEqual({ value: '#ca8a04', name: '옐로' })
  })
})
