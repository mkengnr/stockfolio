export interface GroupColorPreset {
  value: string
  name: string
}

export const GROUP_COLOR_PRESETS: GroupColorPreset[] = [
  { value: '#6366f1', name: '인디고' },
  { value: '#3b82f6', name: '블루' },
  { value: '#06b6d4', name: '시안' },
  { value: '#14b8a6', name: '틸' },
  { value: '#10b981', name: '에메랄드' },
  { value: '#84cc16', name: '라임' },
  { value: '#f59e0b', name: '앰버' },
  { value: '#f97316', name: '오렌지' },
  { value: '#ef4444', name: '레드' },
  { value: '#ec4899', name: '핑크' },
  { value: '#8b5cf6', name: '바이올렛' },
  { value: '#a855f7', name: '퍼플' },
]

// 전체 그룹에서 아직 안 쓰는 첫 프리셋 색을 추천. 전부 사용 중이면 첫 프리셋.
export function recommendGroupColor(usedColors: string[]): string {
  const used = new Set(usedColors.map((color) => color.trim().toLowerCase()))
  const unused = GROUP_COLOR_PRESETS.find((preset) => !used.has(preset.value.toLowerCase()))
  return (unused ?? GROUP_COLOR_PRESETS[0]).value
}
