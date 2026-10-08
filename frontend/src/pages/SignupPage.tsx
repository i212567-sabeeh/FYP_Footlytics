import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router'
import { ROLE_OPTIONS } from '../features/auth/types'
import { submitSignup } from '../features/users/signupApi'
import { useAuth } from '../hooks/useAuth'

const signupRoles = ROLE_OPTIONS.filter((option) => option.value !== 'admin')

export function SignupPage() {
  const { accessToken } = useAuth()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [requestedRole, setRequestedRole] = useState('')
  const [error, setError] = useState('')
  const [receipt, setReceipt] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (accessToken) return <Navigate to="/" replace />

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (!name.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError('Enter your full name and a valid email address.')
      return
    }
    if (password.length < 8 || password.length > 128) {
      setError('Use a password between 8 and 128 characters.')
      return
    }
    if (password !== confirmation) {
      setError('Passwords do not match.')
      return
    }
    const selectedRole = signupRoles.find((option) => option.value === requestedRole)
    if (!selectedRole) {
      setError('Choose the role you are requesting.')
      return
    }
    setSubmitting(true)
    try {
      const result = await submitSignup({ full_name: name.trim(), email: email.trim(), password, requested_role: selectedRole.value })
      setPassword('')
      setConfirmation('')
      setReceipt(result.message)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to submit your request. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return <section className="mx-auto max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6 sm:p-8">
    <p className="text-sm font-semibold uppercase tracking-widest text-emerald-400">Request access</p>
    <h1 className="mt-3 text-3xl font-semibold">Sign up for FOOTLYTICS</h1>
    <p className="mt-3 text-slate-400">Submit your details for administrator approval. You can sign in once your access is approved.</p>
    {receipt ? <div className="mt-8 space-y-4">
      <p role="status" className="rounded-lg border border-emerald-800 bg-emerald-950/40 p-4 text-emerald-200">{receipt}</p>
      <p className="text-sm text-slate-400">Contact your administrator for an update. This page does not send an email notification.</p>
    </div> : <form onSubmit={submit} noValidate className="mt-8">
      <fieldset disabled={submitting} className="space-y-5">
        <div>
          <label htmlFor="signup-name" className="field-label">Full name</label>
          <input id="signup-name" autoComplete="name" required maxLength={200} className="field-input"
            value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div>
          <label htmlFor="signup-email" className="field-label">Email</label>
          <input id="signup-email" type="email" autoComplete="username" required maxLength={254} className="field-input"
            value={email} onChange={(event) => setEmail(event.target.value)} />
        </div>
        <div>
          <label htmlFor="signup-role" className="field-label">Requested role</label>
          <select id="signup-role" required className="field-input" value={requestedRole}
            aria-describedby="signup-role-help" onChange={(event) => setRequestedRole(event.target.value)}>
            <option value="">Select your role</option>
            {signupRoles.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <p id="signup-role-help" className="mt-2 text-sm text-slate-400">An administrator must approve your role and access before you can sign in.</p>
        </div>
        <div>
          <label htmlFor="signup-password" className="field-label">Password</label>
          <input id="signup-password" type="password" autoComplete="new-password" required minLength={8} maxLength={128}
            aria-describedby="signup-password-help" className="field-input" value={password} onChange={(event) => setPassword(event.target.value)} />
          <p id="signup-password-help" className="mt-2 text-sm text-slate-400">8–128 characters.</p>
        </div>
        <div>
          <label htmlFor="signup-confirm" className="field-label">Confirm password</label>
          <input id="signup-confirm" type="password" autoComplete="new-password" required maxLength={128} className="field-input"
            value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
        </div>
        {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
        <button type="submit" className="button-primary w-full">{submitting ? 'Submitting…' : 'Request access'}</button>
      </fieldset>
    </form>}
    <p className="mt-6 text-sm text-slate-400">Already have approved access? <Link to="/login" className="record-link">Sign in</Link></p>
  </section>
}
