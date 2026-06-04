import { AuthForm } from '@/components/auth/AuthForm'

export default function AuthPage({ searchParams }: { searchParams?: { returnTo?: string | string[] } }) {
  const returnTo = typeof searchParams?.returnTo === 'string' ? searchParams.returnTo : undefined

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <AuthForm returnTo={returnTo} />
    </div>
  )
}
