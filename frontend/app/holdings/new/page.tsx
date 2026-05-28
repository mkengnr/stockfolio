import { AuthGuard } from '@/components/layout/AuthGuard'
import { HoldingForm } from '@/components/holdings/HoldingForm'

export default function NewHoldingPage() {
  return (
    <AuthGuard>
      <div>
        <h1 className="mb-6 text-xl font-semibold text-gray-900">종목 등록</h1>
        <HoldingForm />
      </div>
    </AuthGuard>
  )
}
