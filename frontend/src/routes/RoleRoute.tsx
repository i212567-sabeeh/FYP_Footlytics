import { House, ShieldOff } from 'lucide-react'
import { Link, Outlet } from 'react-router'
import { MessagePanel } from '../components/MessagePanel'
import { hasAnyRole, type Role } from '../features/auth/types'
import { useAuth } from '../hooks/useAuth'

export function RoleRoute({ roles }: { roles: readonly Role[] }) {
  const { user } = useAuth()
  if (!hasAnyRole(user, roles)) {
    return <MessagePanel icon={ShieldOff} tone="warning" title="Access denied"
      actions={<Link to="/" className="button-secondary"><House aria-hidden="true" className="size-4" />Return home</Link>}>
      <p>Your account does not have permission to view this page.</p>
    </MessagePanel>
  }
  return <Outlet />
}
