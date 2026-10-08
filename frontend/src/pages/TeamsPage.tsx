import { useState } from 'react'
import { CalendarDays, CirclePlus, Pencil, Shield, Shirt } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router'
import { apiRequest } from '../api/client'
import { useRecord, useRecords } from '../features/football/api'
import { ClubPicker, NameForm, type NameValue } from '../features/football/forms'
import { RecordHeader } from '../features/football/RecordHeader'
import { SquadPanel } from '../features/football/SquadPanel'
import type { Team } from '../features/football/types'
import { Empty, FilterPanel, Heading, Pager, QueryState, RecordRow, Status } from '../features/football/ui'
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
  return <section><Heading title="Teams" description="Teams belong to one club. Squad membership keeps history; ending a membership never deletes the player.">
    {roster && <button className="button-primary" onClick={() => { save.reset(); setCreating(true) }}><CirclePlus aria-hidden="true" className="size-4" />Create team</button>}</Heading>
    {creating && <NameForm kind="team" saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setCreating(false)} />}
    <FilterPanel filtered={Boolean(club || active)} onClear={() => { setParams({}); setActive(''); setOffset(0) }}>
      <ClubPicker all value={club} onChange={(value) => { setParams(value ? { club_id: value } : {}); setOffset(0) }} /><ActiveFilter value={active} onChange={(value) => { setActive(value); setOffset(0) }} /></FilterPanel>
    <QueryState query={teams} />{teams.data && <>{teams.data.items.length > 0 && <ul className="panel divide-y divide-line px-5 py-0">{teams.data.items.map((team) => <RecordRow key={team.id} to={`/teams/${team.id}`}
      name={team.name} meta={<>{team.club.name}{team.description && <span className="text-slate-500"> · {team.description}</span>}</>} status={<Status active={team.is_active} />} />)}</ul>}
      {!teams.data.total && <Empty>No teams found. Choose another filter or ask your club coach to add a team.</Empty>}<Pager total={teams.data.total} offset={offset} onChange={setOffset} /></>}
  </section>
}
export function TeamDetailPage() {
  const { teamId } = useParams()
  const team = useRecord<Team>(`teams/${teamId}`)
  const [editing, setEditing] = useState(false)
  const { roster } = useCapabilities()
  const save = useSave((data: NameValue) => apiRequest(`teams/${teamId}`, { method: 'PATCH', body: { name: data.name, short_name: data.short_name, description: data.description, is_active: data.is_active } }), () => setEditing(false))
  return <section><QueryState query={team} />{team.data && <>
    <RecordHeader eyebrow="Team" icon={Shirt} title={team.data.name} back={{ to: '/teams', label: 'All teams' }}
      badges={<><Status active={team.data.is_active} /><Link className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-2.5 py-0.5 font-medium text-slate-300 hover:text-emerald-200" to={`/clubs/${team.data.club_id}`}>
        <Shield aria-hidden="true" className="size-3.5" />{team.data.club.name}</Link></>}
      actions={<>
        <Link className="button-secondary" to={`/matches?club_id=${team.data.club_id}&team_id=${team.data.id}`}><CalendarDays aria-hidden="true" className="size-4" />Team matches</Link>
        {roster && team.data.club.is_active && <button className="button-secondary" onClick={() => { save.reset(); setEditing(true) }}><Pencil aria-hidden="true" className="size-4" />Edit team</button>}
      </>}>
      <p className="text-slate-300">{team.data.description || 'No description recorded.'}</p>
    </RecordHeader>
    {editing && <NameForm kind="team" initial={team.data} saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setEditing(false)} />}
    <SquadPanel key={team.data.id} team={team.data} />
  </>}</section>
}
