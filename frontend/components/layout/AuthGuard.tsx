'use client'

import { useAuth } from '@/hooks/useAuth'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { Navbar } from './Navbar'

interface Props {
  children: React.ReactNode
  adminOnly?: boolean
}

export function AuthGuard({ children, adminOnly = false }: Props) {
  const { user, isLoading, isAuthenticated } = useAuth({ required: true })

  if (isLoading) return <PageLoader />
  if (!isAuthenticated) return null  // useAuth will redirect to /auth

  if (adminOnly && !user?.is_admin) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-2">
        <p className="text-lg font-semibold text-gray-700">접근 권한이 없습니다</p>
        <p className="text-sm text-gray-400">관리자 계정만 접근 가능합니다.</p>
      </div>
    )
  }

  return (
    <>
      <Navbar />
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
    </>
  )
}
