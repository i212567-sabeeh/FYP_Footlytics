import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { apiRequest } from '../api/client'
import { useRecord, useRecords } from '../features/football/api'
import { ClubPicker, PlayerForm, TeamFilter, type PlayerValue } from '../features/football/forms'
import { playerName, type FootballPlayer, type SquadMembership } from '../features/football/types'
import { DateText, Empty, Heading, Pager, QueryState, Status } from '../features/football/ui'
import { useCapabilities, useSave } from '../features/football/hooks'
import { ActiveFilter } from './ClubsPage'

export function PlayersPage() {
  const [params, setParams] = useSearchParams()
  const club = params.get('club_id') ?? ''
  const [team, setTeam] = useState('')
  const [active, setActive] = useState('')
  const [offset, setOffset] = useState(0)
  const [creating, setCreating] = useState(false)
  const { roster } = useCapabilities()
  const players = useRecords<FootballPlayer>('players', { club_id: club, team_id: team, active, offset, limit: 25 })
  const save = useSave((data: PlayerValue) => {
    const { is_active: _active, ...body } = data
    void _active
    return apiRequest('players', { method: 'POST', body })
  }, () => setCreating(false))
  return <section><Heading title="Football players">{roster && <button className="button-primary" onClick={() => { save.reset(); setCreating(true) }}>Create player</button>}</Heading>
    <p className="mb-6 text-slate-400">Football records are separate from login accounts. A player does not need a user account.</p>
    {creating && <PlayerForm saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setCreating(false)} />}
    <div className="mb-6 grid gap-4 sm:grid-cols-3"><ClubPicker all value={club} onChange={(value) => { setParams(value ? { club_id: value } : {}); setTeam(''); setOffset(0) }} />
      <TeamFilter club={club} value={team} onChange={(value) => { setTeam(value); setOffset(0) }} /><ActiveFilter value={active} onChange={(value) => { setActive(value); setOffset(0) }} /></div>
    <QueryState query={players} />{players.data && <><div className="grid gap-4 sm:grid-cols-2">{players.data.items.map((player) => <article className="panel" key={player.id}>
      <div className="flex justify-between gap-4"><Link className="record-link text-lg" to={`/players/${player.id}`}>{playerName(player)}</Link><Status active={player.is_active} /></div>
      <p className="mt-3 text-slate-400">{player.club.name} · <span className="capitalize">{player.preferred_position || 'Position not recorded'}</span></p>
    </article>)}</div>{!players.data.total && <Empty>No football players found. Player accounts need an active linked profile and club assignment to see their own data.</Empty>}<Pager total={players.data.total} offset={offset} onChange={setOffset} /></>}
  </section>
}
export function PlayerDetailPage() {
  const { playerId } = useParams()
  const player = useRecord<FootballPlayer>(`players/${playerId}`)
  const [offset, setOffset] = useState(0)
  const squads = useRecords<SquadMembership>(`players/${playerId}/squads`, { offset, limit: 25 }, !!player.data)
  const [editing, setEditing] = useState(false)
  const { roster } = useCapabilities()
  const save = useSave((data: PlayerValue) => {
    const { club_id: _club, ...body } = data
    void _club
    return apiRequest(`players/${playerId}`, { method: 'PATCH', body })
  }, () => setEditing(false))
  return <section><Link className="record-link" to="/players">All players</Link><QueryState query={player} />{player.data && <>
    <div className="mt-6"><Heading title={playerName(player.data)}>{roster && player.data.club.is_active && <button className="button-secondary" onClick={() => { save.reset(); setEditing(true) }}>Edit player</button>}</Heading></div>
    {editing && <PlayerForm initial={player.data} saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setEditing(false)} />}
    <div className="panel"><dl className="grid gap-5 sm:grid-cols-2">
      <div><dt className="text-sm text-slate-500">Club</dt><dd><Link className="record-link" to={`/clubs/${player.data.club_id}`}>{player.data.club.name}</Link></dd></div>
      <div><dt className="text-sm text-slate-500">Full name</dt><dd>{player.data.first_name} {player.data.last_name}</dd></div>
      <div><dt className="text-sm text-slate-500">Preferred position</dt><dd className="capitalize">{player.data.preferred_position || 'Not recorded'}</dd></div>
      <div><dt className="text-sm text-slate-500">Date of birth</dt><dd>{player.data.date_of_birth || 'Not recorded'}</dd></div>
      <div><dt className="text-sm text-slate-500">Linked login account</dt><dd>{player.data.linked_user?.full_name || 'No account linked'}</dd></div>
      <div><dt className="text-sm text-slate-500">Status</dt><dd><Status active={player.data.is_active} /></dd></div>
    </dl></div>
    <section className="panel mt-8"><h2 className="mb-4 text-xl font-semibold">Squad memberships</h2><QueryState query={squads} />{squads.data && <>
      <ul className="divide-y divide-slate-800">{squads.data.items.map((membership) => <li className="py-4" key={membership.id}><div className="flex justify-between gap-4"><Link className="record-link" to={`/teams/${membership.team_id}`}>{membership.team.name}</Link><Status active={membership.is_active} /></div>
        <p className="mt-2 text-sm text-slate-400">Shirt: {membership.shirt_number ?? 'Unassigned'} · Joined: <DateText value={membership.joined_at} />{membership.left_at && <> · Left: <DateText value={membership.left_at} /></>}</p>
      </li>)}</ul>{!squads.data.total && <p className="text-slate-400">No accessible squad memberships.</p>}<Pager total={squads.data.total} offset={offset} onChange={setOffset} />
    </>}</section>
  </>}</section>
}
