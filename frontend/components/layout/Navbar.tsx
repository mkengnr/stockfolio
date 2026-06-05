'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import { authApi } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/Button'

const navLinks = [
  { href: '/', label: '대시보드' },
  { href: '/transactions', label: '거래내역' },
  { href: '/holdings/new', label: '종목 등록' },
  { href: '/tags', label: '그룹 관리' },
]

export function Navbar() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, mutate } = useAuth()
  const [loggingOut, setLoggingOut] = useState(false)

  async function handleLogout() {
    setLoggingOut(true)
    try {
      await authApi.logout()
      await mutate(undefined, { revalidate: false })
      router.replace('/auth')
    } finally {
      setLoggingOut(false)
    }
  }

  return (
    <header className="sticky top-0 z-30 border-b border-gray-200 bg-white">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2 font-bold text-brand-600 text-lg">
            📈 stockfolio
          </Link>
          <nav className="hidden sm:flex items-center gap-1">
            {navLinks.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  pathname === href || (href === '/tags' && pathname.startsWith('/tags/'))
                    ? 'bg-brand-50 text-brand-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
                )}
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          {user?.is_admin && (
            <Link href="/admin" className="text-xs text-gray-400 hover:text-gray-600">
              관리자
            </Link>
          )}
          <span className="hidden text-sm text-gray-500 sm:block">{user?.email}</span>
          <Button variant="ghost" size="sm" loading={loggingOut} onClick={handleLogout}>
            로그아웃
          </Button>
        </div>
      </div>
    </header>
  )
}
