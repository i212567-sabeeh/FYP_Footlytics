import { Link, Outlet } from 'react-router'
import { hasRole } from '../features/auth/types'
import { useAuth } from '../hooks/useAuth'

export function AppLayout() {
  const { user, logout } = useAuth()
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:p-4">
        Skip to content
      </a>
      <header className="border-b border-slate-800">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-6">
          <Link to="/" className="text-lg font-bold tracking-widest text-emerald-400">
            FOOTLYTICS
          </Link>
          {user ? (
            <nav aria-label="Main navigation" className="flex flex-wrap items-center gap-5 text-sm">
              <Link to="/">Home</Link>
              <Link to="/clubs">Clubs</Link>
              <Link to="/teams">Teams</Link>
              <Link to="/players">Players</Link>
              <Link to="/matches">Matches</Link>
              {hasRole(user, 'admin') && <>
                <Link to="/admin/users">User management</Link>
                <Link to="/admin/signup-requests">Access requests</Link>
              </>}
              <button className="button-secondary" onClick={logout}>Logout</button>
            </nav>
          ) : <span className="text-sm text-slate-400">Post-match analysis</span>}
        </div>
      </header>
      <main id="main-content" className="mx-auto max-w-6xl px-6 py-12">
        <Outlet />
      </main>
    </div>
  )
}
