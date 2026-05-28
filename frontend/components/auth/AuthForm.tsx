'use client'

import { useState, useRef, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { authApi } from '@/lib/api'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'

type Step = 'email' | 'otp'

export function AuthForm() {
  const router = useRouter()
  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState<string[]>(Array(6).fill(''))
  const [rememberMe, setRememberMe] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    if (step === 'otp') inputRefs.current[0]?.focus()
  }, [step])

  async function handleEmailSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await authApi.requestOtp(email)
      setSent(true)
      setStep('otp')
    } catch (err: unknown) {
      // Always show success message to avoid email enumeration
      setSent(true)
      setStep('otp')
    } finally {
      setLoading(false)
    }
  }

  async function handleOtpSubmit(e: React.FormEvent) {
    e.preventDefault()
    const code = otp.join('')
    if (code.length !== 6) {
      setError('6자리 코드를 모두 입력해주세요.')
      return
    }
    setError('')
    setLoading(true)
    try {
      await authApi.verifyOtp(email, code, rememberMe)
      router.replace('/')
    } catch {
      setError('코드가 올바르지 않거나 만료되었습니다.')
      setOtp(Array(6).fill(''))
      inputRefs.current[0]?.focus()
    } finally {
      setLoading(false)
    }
  }

  function handleOtpChange(index: number, value: string) {
    if (!/^\d*$/.test(value)) return
    const char = value.slice(-1)
    const newOtp = [...otp]
    newOtp[index] = char
    setOtp(newOtp)
    if (char && index < 5) {
      inputRefs.current[index + 1]?.focus()
    }
  }

  function handleOtpKeyDown(index: number, e: React.KeyboardEvent) {
    if (e.key === 'Backspace' && !otp[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
    }
    if (e.key === 'ArrowLeft' && index > 0) inputRefs.current[index - 1]?.focus()
    if (e.key === 'ArrowRight' && index < 5) inputRefs.current[index + 1]?.focus()
  }

  function handleOtpPaste(e: React.ClipboardEvent) {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (pasted.length === 6) {
      setOtp(pasted.split(''))
      inputRefs.current[5]?.focus()
    }
  }

  return (
    <div className="w-full max-w-sm">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-bold text-brand-600">📈 stockfolio</h1>
        <p className="mt-2 text-sm text-gray-500">
          {step === 'email' ? '이메일로 로그인하세요' : `${email}로 코드를 발송했습니다`}
        </p>
      </div>

      {step === 'email' ? (
        <form onSubmit={handleEmailSubmit} className="flex flex-col gap-4">
          <Input
            label="이메일"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <Button type="submit" loading={loading} className="w-full">
            인증 코드 받기
          </Button>
        </form>
      ) : (
        <form onSubmit={handleOtpSubmit} className="flex flex-col gap-6">
          <div>
            <p className="mb-3 text-sm font-medium text-gray-700 text-center">
              6자리 인증 코드 입력
            </p>
            <div className="flex justify-center gap-2" onPaste={handleOtpPaste}>
              {otp.map((digit, i) => (
                <input
                  key={i}
                  ref={(el) => { inputRefs.current[i] = el }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleOtpChange(i, e.target.value)}
                  onKeyDown={(e) => handleOtpKeyDown(i, e)}
                  className="h-12 w-10 rounded-lg border border-gray-300 text-center text-xl font-semibold text-gray-900
                    focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500
                    transition-colors"
                  aria-label={`코드 ${i + 1}번째 자리`}
                />
              ))}
            </div>
          </div>

          <label className="flex cursor-pointer items-center justify-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
            />
            30일 로그인 유지
          </label>

          {error && <p className="text-center text-sm text-red-500">{error}</p>}

          <Button type="submit" loading={loading} className="w-full">
            로그인
          </Button>

          <button
            type="button"
            onClick={() => { setStep('email'); setOtp(Array(6).fill('')); setError('') }}
            className="text-center text-sm text-gray-400 hover:text-gray-600"
          >
            이메일 다시 입력
          </button>
        </form>
      )}
    </div>
  )
}
