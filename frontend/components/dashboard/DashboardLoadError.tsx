'use client'

import { Button } from '@/components/ui/Button'

export function DashboardLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-xl border border-red-100 bg-red-50">
      <p className="text-sm text-red-600">대시보드 정보를 불러오지 못했습니다.</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>다시 시도</Button>
    </div>
  )
}
