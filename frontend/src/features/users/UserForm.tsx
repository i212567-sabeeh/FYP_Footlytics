import { useState, type FormEvent } from 'react'
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

  return (
    <form onSubmit={submit} noValidate className="rounded-xl border border-slate-700 bg-slate-900 p-6">
      <h2 className="mb-6 text-xl font-semibold">{user ? `Edit ${user.full_name}` : 'Create user'}</h2>
      <fieldset disabled={saving} className="space-y-5">
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
        {!user && <div>
          <label className="field-label" htmlFor="user-password">Initial password</label>
          <input id="user-password" type="password" autoComplete="new-password" required
            minLength={8} maxLength={128} className="field-input" value={password}
            onChange={(event) => setPassword(event.target.value)} />
          <p className="mt-2 text-sm text-slate-400">8–128 characters.</p>
        </div>}
        <fieldset>
          <legend className="field-label">Roles</legend>
          <div className="flex flex-wrap gap-4">
            {ROLE_OPTIONS.map((role) => (
              <label key={role.value} className="flex items-center gap-2 text-sm">
                <input type="checkbox" value={role.value} checked={roles.includes(role.value)}
                  disabled={editingSelf && role.value === 'admin'}
                  onChange={(event) => setRoles(event.target.checked
                    ? [...roles, role.value] : roles.filter((value) => value !== role.value))} />
                {role.label}
              </label>
            ))}
          </div>
        </fieldset>
        {user && <label className="flex items-center gap-2">
          <input type="checkbox" checked={active} disabled={editingSelf}
            onChange={(event) => setActive(event.target.checked)} />
          Active account
        </label>}
        {editingSelf && <p className="text-sm text-slate-400">Your own admin role and active status are protected.</p>}
        {(validation || error) && <p role="alert" className="text-sm text-red-300">{validation || error}</p>}
        <div className="flex gap-3">
          <button type="submit" className="button-primary">{saving ? 'Saving…' : 'Save user'}</button>
          <button type="button" onClick={onCancel} className="button-secondary">Cancel</button>
        </div>
      </fieldset>
    </form>
  )
}
