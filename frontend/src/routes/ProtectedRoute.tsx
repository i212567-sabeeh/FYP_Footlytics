import { LoaderCircle, LogOut, RotateCw, ShieldAlert } from 'lucide-react'
import { Navigate, Outlet, useLocation } from 'react-router'
import { MessagePanel } from '../components/MessagePanel'
import { useAuth } from '../hooks/useAuth'

export function ProtectedRoute() {
  const auth = useAuth()
  const location = useLocation()
  if (!auth.accessToken) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (auth.isLoading) return <p role="status" className="flex items-center gap-2 py-8 text-sm text-slate-400">
    <LoaderCircle aria-hidden="true" className="size-4 animate-spin text-emerald-400 motion-reduce:animate-none" />Checking your session…</p>
  if (auth.error) {
    return <MessagePanel icon={ShieldAlert} tone="danger" title="Unable to verify your session" actions={<>
      <button className="button-primary" onClick={auth.retrySession}><RotateCw aria-hidden="true" className="size-4" />Try again</button>
      <button className="button-secondary" onClick={auth.logout}><LogOut aria-hidden="true" className="size-4" />Sign out</button>
    </>}>
      <p role="alert">{auth.error.message}</p>
    </MessagePanel>
  }
  return auth.user ? <Outlet /> : <Navigate to="/login" replace />
}
