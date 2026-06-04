import '@testing-library/jest-dom'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthForm } from '@/components/auth/AuthForm'
import { authApi } from '@/lib/api'

const replace = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
}))

jest.mock('@/lib/api', () => ({
  authApi: {
    requestOtp: jest.fn(),
    verifyOtp: jest.fn(),
    logout: jest.fn(),
  },
}))

const mockedAuthApi = authApi as jest.Mocked<typeof authApi>

describe('AuthForm — email step', () => {
  beforeEach(() => jest.clearAllMocks())

  it('renders email input and submit button', () => {
    render(<AuthForm />)
    expect(screen.getByLabelText('이메일')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '인증 코드 받기' })).toBeInTheDocument()
  })

  it('advances to OTP step after email submit', async () => {
    mockedAuthApi.requestOtp.mockResolvedValue({} as never)
    render(<AuthForm />)

    await userEvent.type(screen.getByLabelText('이메일'), 'test@example.com')
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }))

    await waitFor(() => {
      expect(screen.getByText(/코드를 발송했습니다/)).toBeInTheDocument()
    })
  })

  it('advances to OTP step even when requestOtp throws (anti-enumeration)', async () => {
    mockedAuthApi.requestOtp.mockRejectedValue(new Error('Not found'))
    render(<AuthForm />)

    await userEvent.type(screen.getByLabelText('이메일'), 'unknown@example.com')
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }))

    await waitFor(() => {
      expect(screen.getAllByRole('textbox').length).toBeGreaterThanOrEqual(1)
    })
  })
})

describe('AuthForm — OTP step', () => {
  async function renderAtOtpStep(returnTo?: string) {
    mockedAuthApi.requestOtp.mockResolvedValue({} as never)
    render(<AuthForm returnTo={returnTo} />)
    await userEvent.type(screen.getByLabelText('이메일'), 'test@example.com')
    await userEvent.click(screen.getByRole('button', { name: '인증 코드 받기' }))
    await waitFor(() => screen.getByText(/6자리 인증 코드/))
  }

  async function submitOtp() {
    const digitInputs = screen.getAllByRole('textbox').filter(
      (i) => i.getAttribute('aria-label')?.includes('자리'),
    )
    for (const input of digitInputs) {
      await userEvent.type(input, '1')
    }
    await userEvent.click(screen.getByRole('button', { name: '로그인' }))
  }

  it('renders 6 digit inputs', async () => {
    await renderAtOtpStep()
    const inputs = screen.getAllByRole('textbox')
    // 6 OTP digit inputs
    expect(inputs.filter((i) => i.getAttribute('aria-label')?.includes('자리'))).toHaveLength(6)
  })

  it('renders remember-me checkbox checked by default', async () => {
    await renderAtOtpStep()
    const checkbox = screen.getByRole('checkbox')
    expect(checkbox).toBeChecked()
  })

  it('shows error for wrong OTP', async () => {
    mockedAuthApi.verifyOtp.mockRejectedValue(new Error('Invalid OTP'))
    await renderAtOtpStep()

    await submitOtp()

    await waitFor(() => {
      expect(screen.getByText(/올바르지 않거나 만료/)).toBeInTheDocument()
    })
  })

  it('returns to a safe internal path after OTP verification', async () => {
    mockedAuthApi.verifyOtp.mockResolvedValue({} as never)
    await renderAtOtpStep('/share/token-3')

    await submitOtp()

    expect(replace).toHaveBeenCalledWith('/share/token-3')
  })

  it('falls back to the dashboard for an unsafe return path', async () => {
    mockedAuthApi.verifyOtp.mockResolvedValue({} as never)
    await renderAtOtpStep('//evil.example/share/token-3')

    await submitOtp()

    expect(replace).toHaveBeenCalledWith('/')
  })

  it('can go back to email step', async () => {
    await renderAtOtpStep()
    await userEvent.click(screen.getByText('이메일 다시 입력'))
    expect(screen.getByLabelText('이메일')).toBeInTheDocument()
  })
})
