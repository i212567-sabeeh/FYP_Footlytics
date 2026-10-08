import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router'
import { ApiError } from '../api/client'
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

  return (
    <section className="mx-auto max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6 sm:p-8">
      <p className="text-sm font-semibold uppercase tracking-widest text-emerald-400">Welcome back</p>
      <h1 className="mt-3 text-3xl font-semibold">Sign in to FOOTLYTICS</h1>
      <p className="mt-3 text-slate-400">Sign in with your approved account. New signup requests need administrator approval.</p>
      <form onSubmit={submit} noValidate className="mt-8 space-y-5">
        <div>
          <label htmlFor="login-email" className="field-label">Email</label>
          <input id="login-email" type="email" autoComplete="username" required maxLength={254}
            value={email} onChange={(event) => setEmail(event.target.value)} className="field-input" />
        </div>
        <div>
          <label htmlFor="login-password" className="field-label">Password</label>
          <input id="login-password" type="password" autoComplete="current-password" required maxLength={128}
            value={password} onChange={(event) => setPassword(event.target.value)} className="field-input" />
        </div>
        {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
        <button type="submit" disabled={submitting} className="button-primary w-full">
          {submitting ? 'Signing in…' : 'Sign In'}
        </button>
      </form>
      <p className="mt-6 text-sm text-slate-400">Need an account? <Link to="/signup" className="record-link">Sign up</Link></p>
    </section>
  )
}
