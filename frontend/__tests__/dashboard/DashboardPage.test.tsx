import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { DashboardLoadError } from '@/components/dashboard/DashboardLoadError'

describe('DashboardLoadError', () => {
  it('offers a retry action for portfolio API failures', () => {
    const onRetry = jest.fn()

    render(<DashboardLoadError onRetry={onRetry} />)
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }))

    expect(screen.getByText('대시보드 정보를 불러오지 못했습니다.')).toBeInTheDocument()
    expect(onRetry).toHaveBeenCalled()
  })
})
