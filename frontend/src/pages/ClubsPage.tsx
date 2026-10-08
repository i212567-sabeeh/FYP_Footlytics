import { useState, type FormEvent } from 'react'
import { CalendarDays, CirclePlus, Pencil, Shield, Shirt, UserMinus, UserPlus, Users } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { apiRequest } from '../api/client'
import type { User } from '../features/auth/types'
import { useOptions, useRecord, useRecords } from '../features/football/api'
import { NameForm, type NameValue } from '../features/football/forms'
import { Chip, RecordHeader } from '../features/football/RecordHeader'
import type { Club, ClubMember } from '../features/football/types'
import { Empty, ErrorMessage, Field, FilterPanel, Heading, Initials, Pager, QueryState, RecordRow, Status } from '../features/football/ui'
import { useCapabilities, useSave } from '../features/football/hooks'

export function ClubsPage() {
  const [offset, setOffset] = useState(0)
  const [active, setActive] = useState('')
  const [creating, setCreating] = useState(false)
  const capabilities = useCapabilities()
  const clubs = useRecords<Club>('clubs', { offset, limit: 25, active })
  const save = useSave((data: NameValue) => apiRequest('clubs', { method: 'POST', body: {
    name: data.name, short_name: data.short_name, description: data.description,
  } }), () => setCreating(false))
  return <section><Heading title="Clubs" description="Your accessible clubs. Club assignments control access to teams, players and matches.">
    {capabilities.admin && <button className="button-primary" onClick={() => { save.reset(); setCreating(true) }}><CirclePlus aria-hidden="true" className="size-4" />Create club</button>}</Heading>
    {creating && <NameForm kind="club" saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setCreating(false)} />}
    <FilterPanel filtered={active !== ''} onClear={() => { setActive(''); setOffset(0) }}><ActiveFilter value={active} onChange={(value) => { setActive(value); setOffset(0) }} /></FilterPanel>
    <QueryState query={clubs} />
    {clubs.data && <>{clubs.data.items.length > 0 && <ul className="panel divide-y divide-line px-5 py-0">{clubs.data.items.map((club) => <RecordRow key={club.id} to={`/clubs/${club.id}`}
      name={club.name} meta={club.description || 'No description recorded.'} status={<Status active={club.is_active} />} />)}</ul>}
      {!clubs.data.total && <Empty>No clubs available. An administrator can create a club and assign your account.</Empty>}
      <Pager total={clubs.data.total} offset={offset} onChange={setOffset} /></>}
  </section>
}
export function ActiveFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <Field label="Status"><select className="field-input" value={value} onChange={(e) => onChange(e.target.value)}><option value="">All statuses</option><option value="true">Active</option><option value="false">Inactive</option></select></Field>
}
const CLUB_LINKS = [['teams', 'Teams', Shirt], ['players', 'Players', Users], ['matches', 'Matches', CalendarDays]] as const
export function ClubDetailPage() {
  const { clubId } = useParams()
  const club = useRecord<Club>(`clubs/${clubId}`)
  const [editing, setEditing] = useState(false)
  const { admin } = useCapabilities()
  const save = useSave((data: NameValue) => apiRequest(`clubs/${clubId}`, { method: 'PATCH', body: {
    name: data.name, short_name: data.short_name, description: data.description, is_active: data.is_active,
  } }), () => setEditing(false))
  return <section><QueryState query={club} />
    {club.data && <>
      <RecordHeader eyebrow="Club" icon={Shield} title={club.data.name} back={{ to: '/clubs', label: 'All clubs' }}
        badges={<><Status active={club.data.is_active} />{club.data.short_name && <Chip>Short name: {club.data.short_name}</Chip>}</>}
        actions={admin && <button className="button-secondary" onClick={() => { save.reset(); setEditing(true) }}><Pencil aria-hidden="true" className="size-4" />Edit club</button>}>
        <p className="text-slate-300">{club.data.description || 'No description recorded.'}</p>
        <div className="mt-4 flex flex-wrap gap-2">{CLUB_LINKS.map(([resource, label, Icon]) => <Link key={resource} className="button-secondary min-h-9 px-3 py-1.5" to={`/${resource}?club_id=${club.data!.id}`}>
          <Icon aria-hidden="true" className="size-4" />{label}</Link>)}</div>
      </RecordHeader>
      {editing && <NameForm kind="club" initial={club.data} saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setEditing(false)} />}
      {admin && <ClubMembers club={club.data} />}
    </>}
  </section>
}
function ClubMembers({ club }: { club: Club }) {
  const [offset, setOffset] = useState(0)
  const [account, setAccount] = useState('')
  const [confirming, setConfirming] = useState<number | null>(null)
  const members = useRecords<ClubMember>(`clubs/${club.id}/members`, { offset, limit: 25 })
  const users = useOptions<User>('users')
  const add = useSave((userId: number) => apiRequest(`clubs/${club.id}/members`, { method: 'POST', body: { user_id: userId } }), () => setAccount(''))
  const remove = useSave((userId: number) => apiRequest(`clubs/${club.id}/members/${userId}`, { method: 'DELETE' }), () => setConfirming(null))
  function submit(e: FormEvent) { e.preventDefault(); if (account) add.mutate(Number(account)) }
  return <section className="panel mt-8" aria-labelledby="club-members-heading"><h2 id="club-members-heading" className="mb-2 flex items-center gap-2 text-xl font-semibold"><Users aria-hidden="true" className="size-5 text-emerald-300" />Club members</h2>
    <p className="mb-6 text-sm text-slate-400">Assign existing accounts to this club. Their global roles determine what they can do. Removing an assignment immediately revokes club access.</p>
    {club.is_active && <form onSubmit={submit} className="mb-6 flex flex-wrap items-end gap-3 rounded-xl border border-line bg-canvas/40 p-4"><div className="min-w-60 flex-1"><Field label="Account to assign"><select className="field-input" required value={account} disabled={users.isPending || !!users.error || add.isPending} onChange={(e) => setAccount(e.target.value)}>
      <option value="">Select an active account</option>{users.data?.filter((user) => user.is_active).map((user) => <option key={user.id} value={user.id}>{user.full_name} · {user.email}</option>)}
    </select></Field></div><button className="button-primary" disabled={!account || add.isPending}><UserPlus aria-hidden="true" className="size-4" />Assign member</button></form>}
    <ErrorMessage error={users.error || add.error || remove.error} /><QueryState query={members} />
    {members.data && <><ul className="divide-y divide-line">{members.data.items.map((member) => <li className="flex flex-wrap items-center justify-between gap-3 py-3" key={member.id}>
      <span className="flex min-w-0 items-center gap-3"><Initials name={member.user.full_name} className="size-8 text-xs" /><span className="truncate">{member.user.full_name} <span className="text-sm text-slate-500">#{member.user_id}</span></span></span>
      {confirming === member.user_id ? <span className="flex flex-wrap items-center gap-2 text-sm text-slate-300">Remove club access?
        <button className="button-secondary min-h-8 px-3 py-1 text-xs text-red-300" disabled={remove.isPending} onClick={() => remove.mutate(member.user_id)}>Confirm removal</button>
        <button className="button-secondary min-h-8 px-3 py-1 text-xs" disabled={remove.isPending} onClick={() => setConfirming(null)}>Keep access</button></span>
        : <button className="button-secondary min-h-8 px-3 py-1 text-xs" disabled={remove.isPending} onClick={() => { remove.reset(); setConfirming(member.user_id) }} aria-label={`Remove ${member.user.full_name} from club`}>
          <UserMinus aria-hidden="true" className="size-3.5" />Remove assignment</button>}
    </li>)}</ul>{!members.data.total && <p className="text-slate-400">No accounts assigned to this club.</p>}<Pager total={members.data.total} offset={offset} onChange={setOffset} /></>}
  </section>
}
