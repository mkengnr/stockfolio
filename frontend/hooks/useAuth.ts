'use client'

import { useEffect } from 'react'
import useSWR from 'swr'
import { useRouter } from 'next/navigation'
import { fetcher } from '@/lib/api'
import type { User } from '@/lib/types'

export function useAuth({ required = false } = {}) {
  const router = useRouter()
  const { data: user, error, isLoading, mutate } = useSWR<User>(
    '/api/auth/me',
    fetcher,
    { shouldRetryOnError: false, revalidateOnFocus: false },
  )

  const isAuthenticated = !!user && !error

  useEffect(() => {
    if (required && !isLoading && !isAuthenticated) {
      router.replace('/auth')
    }
  }, [required, isLoading, isAuthenticated, router])

  return { user, isLoading, isAuthenticated, mutate }
}
