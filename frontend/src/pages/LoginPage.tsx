import { useState, type FormEvent } from 'react'
import { CircleAlert, LoaderCircle, LogIn } from 'lucide-react'
import { Link, Navigate, useLocation } from 'react-router'
import { ApiError } from '../api/client'
import { AuthCard, PasswordInput } from '../features/auth/AuthCard'
import { useAuth } from '../hooks/useAuth'

export function LoginPage() {
  const auth = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const state: unknown = location.state
  const requestedPath = typeof state === 'object' && state !== null && 'from' in state
    ? state.from : '/'
  const destination = typeof requestedPath === 'string' && requestedPath.startsWith('/')
    && !requestedPath.startsWith('//') && requestedPath !== '/login' ? requestedPath : '/'

  if (auth.accessToken) return <Navigate to={destination} replace />

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) || !password) {
      setError('Enter a valid email address and your password.')
      return
    }
    setSubmitting(true)
    try {
      await auth.login({ email: email.trim(), password })
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 401
        ? 'Invalid email or password.'
        : cause instanceof Error ? cause.message : 'Sign-in failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return <AuthCard eyebrow="Welcome back" title="Sign in to FOOTLYTICS" intro="Sign in with your approved account. New signup requests need administrator approval."
    footer={<>Need an account? <Link to="/signup" className="record-link">Sign up</Link></>}>
    <form onSubmit={submit} noValidate className="mt-8 space-y-5">
      <div>
        <label htmlFor="login-email" className="field-label">Email</label>
        <input id="login-email" type="email" autoComplete="username" required maxLength={254}
          value={email} onChange={(event) => setEmail(event.target.value)} className="field-input" />
      </div>
      <div>
        <label htmlFor="login-password" className="field-label">Password</label>
        <PasswordInput id="login-password" autoComplete="current-password" required maxLength={128}
          value={password} onChange={(event) => setPassword(event.target.value)} />
      </div>
      {error && <p role="alert" className="flex items-start gap-2 rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-2.5 text-sm text-red-200">
        <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{error}</p>}
      <button type="submit" disabled={submitting} className="button-primary w-full">
        {submitting ? <LoaderCircle aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" /> : <LogIn aria-hidden="true" className="size-4" />}
        {submitting ? 'Signing in…' : 'Sign In'}
      </button>
    </form>
  </AuthCard>
}
