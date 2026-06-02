import { AuthGuard } from '@/components/layout/AuthGuard'
import { TagManager } from '@/components/tags/TagManager'

export default function TagsPage() {
  return (
    <AuthGuard>
      <TagManager />
    </AuthGuard>
  )
}
