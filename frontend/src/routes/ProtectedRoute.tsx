import { Navigate, Outlet, useLocation } from 'react-router'
import { useAuth } from '../hooks/useAuth'

export function ProtectedRoute() {
  const auth = useAuth()
  const location = useLocation()
  if (!auth.accessToken) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (auth.isLoading) return <p role="status">Checking your session…</p>
  if (auth.error) {
    return (
      <section>
        <h1 className="text-2xl font-semibold">Unable to verify your session</h1>
        <p role="alert" className="mt-4">{auth.error.message}</p>
        <div className="mt-4 flex gap-4">
          <button className="button-primary" onClick={auth.retrySession}>Try again</button>
          <button className="button-secondary" onClick={auth.logout}>Sign out</button>
        </div>
      </section>
    )
  }
  return auth.user ? <Outlet /> : <Navigate to="/login" replace />
}
