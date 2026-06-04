import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import AuthPage from '@/app/auth/page'

jest.mock('@/components/auth/AuthForm', () => ({
  AuthForm: ({ returnTo }: { returnTo?: string }) => <p>{returnTo}</p>,
}))

describe('AuthPage', () => {
  it('passes the requested return path to the auth form', () => {
    render(<AuthPage searchParams={{ returnTo: '/share/token-3' }} />)

    expect(screen.getByText('/share/token-3')).toBeInTheDocument()
  })
})
