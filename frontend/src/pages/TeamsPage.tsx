import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { apiRequest } from '../api/client'
import { useRecord, useRecords } from '../features/football/api'
import { ClubPicker, NameForm, type NameValue } from '../features/football/forms'
import { SquadPanel } from '../features/football/SquadPanel'
import type { Team } from '../features/football/types'
import { Empty, Heading, Pager, QueryState, Status } from '../features/football/ui'
import { useCapabilities, useSave } from '../features/football/hooks'
import { ActiveFilter } from './ClubsPage'

export function TeamsPage() {
  const [params, setParams] = useSearchParams()
  const club = params.get('club_id') ?? ''
  const [active, setActive] = useState('')
  const [offset, setOffset] = useState(0)
  const [creating, setCreating] = useState(false)
  const { roster } = useCapabilities()
  const teams = useRecords<Team>('teams', { club_id: club, active, offset, limit: 25 })
  const save = useSave((data: NameValue) => apiRequest('teams', { method: 'POST', body: { name: data.name, short_name: data.short_name, description: data.description, club_id: data.club_id } }), () => setCreating(false))
  return <section><Heading title="Teams">{roster && <button className="button-primary" onClick={() => { save.reset(); setCreating(true) }}>Create team</button>}</Heading>
    {creating && <NameForm kind="team" saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setCreating(false)} />}
    <div className="mb-6 grid gap-4 sm:grid-cols-2"><ClubPicker all value={club} onChange={(value) => { setParams(value ? { club_id: value } : {}); setOffset(0) }} /><ActiveFilter value={active} onChange={(value) => { setActive(value); setOffset(0) }} /></div>
    <QueryState query={teams} />{teams.data && <><div className="grid gap-4 sm:grid-cols-2">{teams.data.items.map((team) => <article className="panel" key={team.id}>
      <div className="flex justify-between gap-4"><Link to={`/teams/${team.id}`} className="record-link text-lg">{team.name}</Link><Status active={team.is_active} /></div>
      <p className="mt-3 text-slate-400">{team.club.name}</p><p className="mt-2 text-sm text-slate-500">{team.description || 'No description recorded.'}</p>
    </article>)}</div>{!teams.data.total && <Empty>No teams found. Choose another filter or ask your club coach to add a team.</Empty>}<Pager total={teams.data.total} offset={offset} onChange={setOffset} /></>}
  </section>
}
export function TeamDetailPage() {
  const { teamId } = useParams()
  const team = useRecord<Team>(`teams/${teamId}`)
  const [editing, setEditing] = useState(false)
  const { roster } = useCapabilities()
  const save = useSave((data: NameValue) => apiRequest(`teams/${teamId}`, { method: 'PATCH', body: { name: data.name, short_name: data.short_name, description: data.description, is_active: data.is_active } }), () => setEditing(false))
  return <section><Link to="/teams" className="record-link">All teams</Link><QueryState query={team} />{team.data && <>
    <div className="mt-6"><Heading title={team.data.name}>{roster && team.data.club.is_active && <button className="button-secondary" onClick={() => { save.reset(); setEditing(true) }}>Edit team</button>}</Heading></div>
    {editing && <NameForm kind="team" initial={team.data} saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setEditing(false)} />}
    <div className="panel"><Link className="record-link" to={`/clubs/${team.data.club_id}`}>{team.data.club.name}</Link><p className="mt-3"><Status active={team.data.is_active} /></p>
      <p className="mt-3 text-slate-400">{team.data.description || 'No description recorded.'}</p>
      <Link className="record-link mt-4 inline-block" to={`/matches?club_id=${team.data.club_id}&team_id=${team.data.id}`}>Team matches</Link>
    </div><SquadPanel key={team.data.id} team={team.data} />
  </>}</section>
}
