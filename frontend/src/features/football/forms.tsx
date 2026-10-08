import { useState, type FormEvent, type ReactNode } from 'react'
import { useOptions } from './api'
import { ErrorMessage, Field, QueryState } from './ui'
import { POSITIONS, type AccountReference, type Club, type FootballPlayer, type Team } from './types'

interface FormProps<T> { initial?: T; saving: boolean; error: Error | null; onCancel: () => void }
export interface NameFields { name: string; short_name: string | null; description: string | null }
export interface NameValue extends NameFields { club_id: number; is_active: boolean }
export interface PlayerValue {
  club_id: number; first_name: string; last_name: string; display_name: string | null
  date_of_birth: string | null; preferred_position: FootballPlayer['preferred_position']; user_id: number | null; is_active: boolean
}

export function FormButtons({ saving, cancel, label }: { saving: boolean; cancel: () => void; label: string }) {
  return <div className="mt-6 flex gap-3"><button className="button-primary" disabled={saving}>{saving ? 'Saving…' : label}</button>
    <button type="button" className="button-secondary" disabled={saving} onClick={cancel}>Cancel</button></div>
}
export function ClubPicker({ value, onChange, disabled = false, all = false }: {
  value: string; onChange: (value: string) => void; disabled?: boolean; all?: boolean
}) {
  const clubs = useOptions<Club>('clubs', all ? {} : { active: true }, !disabled)
  return <Field label="Club"><select className="field-input" required={!all} value={value} disabled={disabled || clubs.isPending} onChange={(e) => onChange(e.target.value)}>
    <option value="">{all ? 'All accessible clubs' : 'Select a club'}</option>
    {clubs.data?.map((club) => <option key={club.id} value={club.id}>{club.name}</option>)}
  </select>{!disabled && <ErrorMessage error={clubs.error} />}</Field>
}
export function FormPanel({ title, children }: { title: string; children: ReactNode }) {
  return <div className="panel mb-8"><h2 className="mb-6 text-xl font-semibold">{title}</h2>{children}</div>
}
export function NameForm({ kind, initial, saving, error, onSave, onCancel }: FormProps<Club | Team> & {
  kind: 'club' | 'team'; onSave: (value: NameValue) => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [shortName, setShortName] = useState(initial?.short_name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [club, setClub] = useState('')
  const [active, setActive] = useState(initial?.is_active ?? true)
  const [validation, setValidation] = useState<Error | null>(null)
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim() || (kind === 'team' && !initial && !club)) { setValidation(new Error('Enter a name and select the club where required.')); return }
    setValidation(null)
    onSave({ name: name.trim(), short_name: shortName.trim() || null, description: description.trim() || null,
      club_id: Number(club), is_active: active })
  }
  return <FormPanel title={`${initial ? 'Edit' : 'Create'} ${kind}`}><form onSubmit={submit}><fieldset disabled={saving} className="space-y-4">
    {kind === 'team' && !initial && <ClubPicker value={club} onChange={setClub} />}
    <Field label="Name"><input className="field-input" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} /></Field>
    <Field label="Short name (optional)"><input className="field-input" maxLength={40} value={shortName} onChange={(e) => setShortName(e.target.value)} /></Field>
    <Field label="Description (optional)"><textarea className="field-input" maxLength={2000} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
    {initial && <label className="flex gap-2"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />Active {kind}</label>}
    <ErrorMessage error={validation || error} /><FormButtons saving={saving} cancel={onCancel} label={`Save ${kind}`} />
  </fieldset></form></FormPanel>
}
export function PlayerForm({ initial, saving, error, onCancel, onSave }: FormProps<FootballPlayer> & { onSave: (value: PlayerValue) => void }) {
  const [club, setClub] = useState(String(initial?.club_id ?? ''))
  const [first, setFirst] = useState(initial?.first_name ?? '')
  const [last, setLast] = useState(initial?.last_name ?? '')
  const [display, setDisplay] = useState(initial?.display_name ?? '')
  const [birth, setBirth] = useState(initial?.date_of_birth ?? '')
  const [position, setPosition] = useState<FootballPlayer['preferred_position']>(initial?.preferred_position ?? null)
  const [account, setAccount] = useState(String(initial?.user_id ?? ''))
  const [active, setActive] = useState(initial?.is_active ?? true)
  const [validation, setValidation] = useState<Error | null>(null)
  const accounts = useOptions<AccountReference>(`clubs/${club}/player-account-options`, {}, !!club)
  const options = accounts.data ?? []
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!club || !first.trim() || !last.trim()) { setValidation(new Error('Select a club and enter first and last names.')); return }
    if (birth && birth > new Date().toISOString().slice(0, 10)) { setValidation(new Error('Date of birth cannot be in the future.')); return }
    setValidation(null)
    onSave({ club_id: Number(club), first_name: first.trim(), last_name: last.trim(), display_name: display.trim() || null,
      date_of_birth: birth || null, preferred_position: position, user_id: account ? Number(account) : null, is_active: active })
  }
  return <FormPanel title={initial ? 'Edit football player' : 'Create football player'}><form onSubmit={submit}><fieldset disabled={saving} className="space-y-4">
    {initial ? <p className="text-slate-400">Club: {initial.club.name}</p> : <ClubPicker value={club} onChange={(value) => { setClub(value); setAccount('') }} />}
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="First name"><input className="field-input" required maxLength={100} value={first} onChange={(e) => setFirst(e.target.value)} /></Field>
      <Field label="Last name"><input className="field-input" required maxLength={100} value={last} onChange={(e) => setLast(e.target.value)} /></Field>
      <Field label="Display name (optional)"><input className="field-input" maxLength={200} value={display} onChange={(e) => setDisplay(e.target.value)} /></Field>
      <Field label="Date of birth (optional)"><input type="date" className="field-input" max={new Date().toISOString().slice(0, 10)} value={birth} onChange={(e) => setBirth(e.target.value)} /></Field>
      <Field label="Preferred position"><select className="field-input" value={position ?? ''} onChange={(e) => setPosition(e.target.value as FootballPlayer['preferred_position'] || null)}>
        <option value="">Not recorded</option>{POSITIONS.map((value) => <option key={value} value={value}>{value}</option>)}
      </select></Field>
      <Field label="Linked login account (optional)"><select className="field-input" value={account} disabled={!club || accounts.isPending || !!accounts.error} onChange={(e) => setAccount(e.target.value)}>
        <option value="">No account linked</option>
        {initial?.linked_user && !options.some((item) => item.id === initial.user_id) && <option value={initial.linked_user.id}>{initial.linked_user.full_name}</option>}
        {options.map((item) => <option key={item.id} value={item.id}>{item.full_name} (#{item.id})</option>)}
      </select><ErrorMessage error={accounts.error} /></Field>
    </div>
    <p className="text-sm text-slate-400">A football player can exist without a login. Eligible accounts must be active club members and can link to one player only.</p>
    {initial && <label className="flex gap-2"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />Active player</label>}
    <ErrorMessage error={validation || error} /><FormButtons saving={saving} cancel={onCancel} label="Save player" />
  </fieldset></form></FormPanel>
}
export function TeamFilter({ club, value, onChange }: { club: string; value: string; onChange: (value: string) => void }) {
  const teams = useOptions<Team>('teams', { club_id: club })
  return <Field label="Team"><select className="field-input" value={value} onChange={(e) => onChange(e.target.value)}>
    <option value="">All accessible teams</option>{teams.data?.map((team) => <option key={team.id} value={team.id}>{team.name} · {team.club.name}</option>)}
  </select><ErrorMessage error={teams.error} /></Field>
}
export { QueryState }
