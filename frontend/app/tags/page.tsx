import { AuthGuard } from '@/components/layout/AuthGuard'
import { GroupManager } from '@/components/groups/GroupManager'

export default function TagsPage() {
  return (
    <AuthGuard>
      <GroupManager />
    </AuthGuard>
  )
}
