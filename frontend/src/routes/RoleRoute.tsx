import { Link, Outlet } from 'react-router'
import { hasAnyRole, type Role } from '../features/auth/types'
import { useAuth } from '../hooks/useAuth'

export function RoleRoute({ roles }: { roles: readonly Role[] }) {
  const { user } = useAuth()
  if (!hasAnyRole(user, roles)) {
    return (
      <section>
        <h1 className="text-2xl font-semibold">Access denied</h1>
        <p className="mt-4 text-slate-300">Your account does not have permission to view this page.</p>
        <Link to="/" className="mt-4 inline-block text-emerald-400 underline">Return home</Link>
      </section>
    )
  }
  return <Outlet />
}
