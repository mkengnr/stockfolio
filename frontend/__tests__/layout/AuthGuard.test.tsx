import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { AuthGuard } from '@/components/layout/AuthGuard'
import { useAuth } from '@/hooks/useAuth'

jest.mock('@/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/components/layout/Navbar', () => ({
  Navbar: () => <nav>navbar</nav>,
}))

const mockedUseAuth = useAuth as jest.Mock

describe('AuthGuard', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('keeps a visible loader while redirecting unauthenticated users', () => {
    mockedUseAuth.mockReturnValue({
      user: undefined,
      isLoading: false,
      isAuthenticated: false,
      mutate: jest.fn(),
    })

    render(
      <AuthGuard>
        <p>private content</p>
      </AuthGuard>,
    )

    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByText('private content')).not.toBeInTheDocument()
  })
})
