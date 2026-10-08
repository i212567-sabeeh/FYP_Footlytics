import { useState, type FormEvent } from 'react'
import { CircleAlert, CircleCheck, LoaderCircle, Send } from 'lucide-react'
import { Link, Navigate } from 'react-router'
import { AuthCard, PasswordInput } from '../features/auth/AuthCard'
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

  return <AuthCard eyebrow="Request access" title="Sign up for FOOTLYTICS" intro="Submit your details for administrator approval. You can sign in once your access is approved."
    footer={<>Already have approved access? <Link to="/login" className="record-link">Sign in</Link></>}>
    {receipt ? <div className="mt-8 space-y-4">
      <p role="status" className="flex items-start gap-2 rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-4 text-emerald-200">
        <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0" />{receipt}</p>
      <p className="text-sm text-slate-400">Contact your administrator for an update. This page does not send an email notification.</p>
    </div> : <form onSubmit={submit} noValidate className="mt-8">
      <fieldset disabled={submitting} className="space-y-5">
        <div className="grid gap-5 sm:grid-cols-2">
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
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor="signup-password" className="field-label">Password</label>
            <PasswordInput id="signup-password" autoComplete="new-password" required minLength={8} maxLength={128}
              aria-describedby="signup-password-help" value={password} onChange={(event) => setPassword(event.target.value)} />
            <p id="signup-password-help" className="mt-2 text-sm text-slate-400">8–128 characters.</p>
          </div>
          <div>
            <label htmlFor="signup-confirm" className="field-label">Confirm password</label>
            <PasswordInput id="signup-confirm" toggleLabel="password confirmation" autoComplete="new-password" required maxLength={128}
              value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
          </div>
        </div>
        {error && <p role="alert" className="flex items-start gap-2 rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-2.5 text-sm text-red-200">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{error}</p>}
        <button type="submit" className="button-primary w-full">
          {submitting ? <LoaderCircle aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" /> : <Send aria-hidden="true" className="size-4" />}
          {submitting ? 'Submitting…' : 'Request access'}</button>
      </fieldset>
    </form>}
  </AuthCard>
}
