import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'
import { apiRequest } from '../api/client'
import type { User } from '../features/auth/types'
import { useOptions, useRecord, useRecords } from '../features/football/api'
import { NameForm, type NameValue } from '../features/football/forms'
import type { Club, ClubMember } from '../features/football/types'
import { Empty, ErrorMessage, Field, Heading, Pager, QueryState, Status } from '../features/football/ui'
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
  return <section><Heading title="Clubs">{capabilities.admin && <button className="button-primary" onClick={() => { save.reset(); setCreating(true) }}>Create club</button>}</Heading>
    <p className="mb-6 text-slate-400">Your accessible clubs. Club assignments control access to teams, players and matches.</p>
    {creating && <NameForm kind="club" saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setCreating(false)} />}
    <div className="mb-6 max-w-xs"><ActiveFilter value={active} onChange={(value) => { setActive(value); setOffset(0) }} /></div>
    <QueryState query={clubs} />
    {clubs.data && <><div className="grid gap-4 sm:grid-cols-2">{clubs.data.items.map((club) => <article className="panel" key={club.id}>
      <div className="flex items-start justify-between gap-4"><Link className="record-link text-lg" to={`/clubs/${club.id}`}>{club.name}</Link><Status active={club.is_active} /></div>
      <p className="mt-3 text-sm text-slate-400">{club.description || 'No description recorded.'}</p>
    </article>)}</div>{!clubs.data.total && <Empty>No clubs available. An administrator can create a club and assign your account.</Empty>}
      <Pager total={clubs.data.total} offset={offset} onChange={setOffset} /></>}
  </section>
}
export function ActiveFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <Field label="Status"><select className="field-input" value={value} onChange={(e) => onChange(e.target.value)}><option value="">All statuses</option><option value="true">Active</option><option value="false">Inactive</option></select></Field>
}
export function ClubDetailPage() {
  const { clubId } = useParams()
  const club = useRecord<Club>(`clubs/${clubId}`)
  const [editing, setEditing] = useState(false)
  const { admin } = useCapabilities()
  const save = useSave((data: NameValue) => apiRequest(`clubs/${clubId}`, { method: 'PATCH', body: {
    name: data.name, short_name: data.short_name, description: data.description, is_active: data.is_active,
  } }), () => setEditing(false))
  return <section><Link to="/clubs" className="record-link">All clubs</Link><QueryState query={club} />
    {club.data && <><div className="mt-6"><Heading title={club.data.name}>{admin && <button className="button-secondary" onClick={() => { save.reset(); setEditing(true) }}>Edit club</button>}</Heading></div>
      {editing && <NameForm kind="club" initial={club.data} saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setEditing(false)} />}
      <div className="panel"><Status active={club.data.is_active} /><p className="mt-3 text-slate-300">{club.data.description || 'No description recorded.'}</p>
        {club.data.short_name && <p className="mt-2 text-slate-400">Short name: {club.data.short_name}</p>}
        <div className="mt-5 flex flex-wrap gap-5">{['teams', 'players', 'matches'].map((resource) => <Link key={resource} className="record-link capitalize" to={`/${resource}?club_id=${club.data!.id}`}>{resource}</Link>)}</div>
      </div>
      {admin && <ClubMembers club={club.data} />}
    </>}
  </section>
}
function ClubMembers({ club }: { club: Club }) {
  const [offset, setOffset] = useState(0)
  const [account, setAccount] = useState('')
  const members = useRecords<ClubMember>(`clubs/${club.id}/members`, { offset, limit: 25 })
  const users = useOptions<User>('users')
  const add = useSave((userId: number) => apiRequest(`clubs/${club.id}/members`, { method: 'POST', body: { user_id: userId } }), () => setAccount(''))
  const remove = useSave((userId: number) => apiRequest(`clubs/${club.id}/members/${userId}`, { method: 'DELETE' }))
  function submit(e: FormEvent) { e.preventDefault(); if (account) add.mutate(Number(account)) }
  return <section className="panel mt-8"><h2 className="mb-3 text-xl font-semibold">Club members</h2>
    <p className="mb-6 text-sm text-slate-400">Assign existing accounts to this club. Their global roles determine what they can do. Removing an assignment immediately revokes club access.</p>
    {club.is_active && <form onSubmit={submit} className="mb-6 flex flex-wrap items-end gap-3"><div className="min-w-60 flex-1"><Field label="Account to assign"><select className="field-input" required value={account} disabled={users.isPending || !!users.error || add.isPending} onChange={(e) => setAccount(e.target.value)}>
      <option value="">Select an active account</option>{users.data?.filter((user) => user.is_active).map((user) => <option key={user.id} value={user.id}>{user.full_name} · {user.email}</option>)}
    </select></Field></div><button className="button-primary mb-2" disabled={!account || add.isPending}>Assign member</button></form>}
    <ErrorMessage error={users.error || add.error || remove.error} /><QueryState query={members} />
    {members.data && <><ul className="divide-y divide-slate-800">{members.data.items.map((member) => <li className="flex items-center justify-between gap-4 py-4" key={member.id}>
      <span>{member.user.full_name} <span className="text-sm text-slate-500">#{member.user_id}</span></span>
      <button className="button-secondary" disabled={remove.isPending} onClick={() => remove.mutate(member.user_id)} aria-label={`Remove ${member.user.full_name} from club`}>Remove assignment</button>
    </li>)}</ul>{!members.data.total && <p className="text-slate-400">No accounts assigned to this club.</p>}<Pager total={members.data.total} offset={offset} onChange={setOffset} /></>}
  </section>
}
