import { useState, type FormEvent, type ReactNode } from 'react'
import { CircleAlert, Save, X } from 'lucide-react'
import { PasswordInput } from '../auth/AuthCard'
import { ROLE_OPTIONS, type Role, type User } from '../auth/types'
import type { UserFields } from './api'

export interface UserFormValue extends UserFields {
  password: string
  is_active: boolean
}

interface UserFormProps {
  user: User | null
  currentUserId: number
  saving: boolean
  error: string | null
  onSave: (values: UserFormValue) => void
  onCancel: () => void
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <div className="space-y-4 border-t border-line pt-5 first:border-t-0 first:pt-0">
    <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{title}</h3>{children}
  </div>
}

export function UserForm({ user, currentUserId, saving, error, onSave, onCancel }: UserFormProps) {
  const [name, setName] = useState(user?.full_name ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [password, setPassword] = useState('')
  const [roles, setRoles] = useState<Role[]>(user?.roles ?? [])
  const [active, setActive] = useState(user?.is_active ?? true)
  const [validation, setValidation] = useState('')
  const editingSelf = user?.id === currentUserId

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!name.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setValidation('Enter a full name and a valid email address.')
      return
    }
    if (!user && (password.length < 8 || password.length > 128)) {
      setValidation('Use a password between 8 and 128 characters.')
      return
    }
    if (roles.length === 0) {
      setValidation('Choose at least one role.')
      return
    }
    setValidation('')
    onSave({ full_name: name.trim(), email: email.trim(), password, roles, is_active: active })
  }

  return <form onSubmit={submit} noValidate className="panel">
    <h2 className="mb-6 text-xl font-semibold">{user ? `Edit ${user.full_name}` : 'Create user'}</h2>
    <fieldset disabled={saving} className="space-y-6">
      <Section title="Account">
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label className="field-label" htmlFor="user-name">Full name</label>
            <input id="user-name" required maxLength={200} autoComplete="name" className="field-input"
              value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div>
            <label className="field-label" htmlFor="user-email">Email</label>
            <input id="user-email" type="email" required maxLength={254} autoComplete="off" className="field-input"
              value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
        </div>
        {!user && <div className="max-w-sm">
          <label className="field-label" htmlFor="user-password">Initial password</label>
          <PasswordInput id="user-password" toggleLabel="initial password" autoComplete="new-password" required
            minLength={8} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} />
          <p className="mt-2 text-sm text-slate-400">8–128 characters.</p>
        </div>}
      </Section>
      <Section title="Roles">
        <fieldset>
          <legend className="sr-only">Roles</legend>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {ROLE_OPTIONS.map((role) => {
              const locked = editingSelf && role.value === 'admin'
              return <label key={role.value} className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors ${roles.includes(role.value)
                ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-100' : 'border-line bg-canvas/40 text-slate-300'} ${locked ? 'opacity-70' : 'cursor-pointer'}`}>
                <input type="checkbox" className="size-4 accent-emerald-400" value={role.value} checked={roles.includes(role.value)} disabled={locked}
                  onChange={(event) => setRoles(event.target.checked ? [...roles, role.value] : roles.filter((value) => value !== role.value))} />
                {role.label}
              </label>
            })}
          </div>
        </fieldset>
      </Section>
      {user && <Section title="Status">
        <label className="flex items-center gap-3 text-sm">
          <input type="checkbox" className="size-4 accent-emerald-400" checked={active} disabled={editingSelf} onChange={(event) => setActive(event.target.checked)} />
          Active account
        </label>
        <p className="text-sm text-slate-400">Inactive accounts cannot sign in. Their records and history are kept.</p>
      </Section>}
      {editingSelf && <p className="text-sm text-slate-400">Your own admin role and active status are protected.</p>}
      {(validation || error) && <p role="alert" className="flex items-start gap-2 rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-2.5 text-sm text-red-200">
        <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{validation || error}</p>}
      <div className="flex flex-wrap gap-3">
        <button type="submit" className="button-primary"><Save aria-hidden="true" className="size-4" />{saving ? 'Saving…' : 'Save user'}</button>
        <button type="button" onClick={onCancel} className="button-secondary"><X aria-hidden="true" className="size-4" />Cancel</button>
      </div>
    </fieldset>
  </form>
}
