import { useState, type ReactNode } from 'react'
import { CirclePlus, Clock3, Pencil, UserRound } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router'
import { apiRequest } from '../api/client'
import { useRecord, useRecords } from '../features/football/api'
import { ClubPicker, PlayerForm, TeamFilter, type PlayerValue } from '../features/football/forms'
import { Chip, RecordHeader } from '../features/football/RecordHeader'
import { playerName, type FootballPlayer, type SquadMembership } from '../features/football/types'
import { DateText, Empty, FilterPanel, Heading, Pager, QueryState, RecordRow, Status } from '../features/football/ui'
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
  return <section><Heading title="Football players" description="Football records are separate from login accounts. A player does not need a user account.">
    {roster && <button className="button-primary" onClick={() => { save.reset(); setCreating(true) }}><CirclePlus aria-hidden="true" className="size-4" />Create player</button>}</Heading>
    {creating && <PlayerForm saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setCreating(false)} />}
    <FilterPanel filtered={Boolean(club || team || active)} onClear={() => { setParams({}); setTeam(''); setActive(''); setOffset(0) }}>
      <ClubPicker all value={club} onChange={(value) => { setParams(value ? { club_id: value } : {}); setTeam(''); setOffset(0) }} />
      <TeamFilter club={club} value={team} onChange={(value) => { setTeam(value); setOffset(0) }} /><ActiveFilter value={active} onChange={(value) => { setActive(value); setOffset(0) }} /></FilterPanel>
    <QueryState query={players} />{players.data && <>{players.data.items.length > 0 && <ul className="panel divide-y divide-line px-5 py-0">{players.data.items.map((player) => <RecordRow key={player.id}
      to={`/players/${player.id}`} name={playerName(player)} meta={<>{player.club.name} · <span className="capitalize">{player.preferred_position || 'Position not recorded'}</span></>}
      status={<Status active={player.is_active} />} />)}</ul>}
      {!players.data.total && <Empty>No football players found. Player accounts need an active linked profile and club assignment to see their own data.</Empty>}<Pager total={players.data.total} offset={offset} onChange={setOffset} /></>}
  </section>
}
function Detail({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0 rounded-lg border border-line bg-canvas/40 px-4 py-3"><dt className="text-xs text-slate-400">{label}</dt><dd className="mt-1 break-words text-slate-100">{children}</dd></div>
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
  return <section><QueryState query={player} />{player.data && <>
    <RecordHeader eyebrow="Football player" icon={UserRound} title={playerName(player.data)} back={{ to: '/players', label: 'All players' }}
      badges={<><Status active={player.data.is_active} /><Chip><span className="capitalize">{player.data.preferred_position || 'Position not recorded'}</span></Chip></>}
      actions={roster && player.data.club.is_active && <button className="button-secondary" onClick={() => { save.reset(); setEditing(true) }}><Pencil aria-hidden="true" className="size-4" />Edit player</button>}>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Detail label="Club"><Link className="record-link" to={`/clubs/${player.data.club_id}`}>{player.data.club.name}</Link></Detail>
        <Detail label="Full name">{player.data.first_name} {player.data.last_name}</Detail>
        <Detail label="Preferred position"><span className="capitalize">{player.data.preferred_position || 'Not recorded'}</span></Detail>
        <Detail label="Date of birth">{player.data.date_of_birth || 'Not recorded'}</Detail>
        <Detail label="Linked login account">{player.data.linked_user?.full_name || 'No account linked'}</Detail>
        <Detail label="Status"><Status active={player.data.is_active} /></Detail>
      </dl>
    </RecordHeader>
    {editing && <PlayerForm initial={player.data} saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setEditing(false)} />}
    <section className="panel" aria-labelledby="squad-history-heading"><h2 id="squad-history-heading" className="mb-4 flex items-center gap-2 text-xl font-semibold"><Clock3 aria-hidden="true" className="size-5 text-emerald-300" />Squad memberships</h2>
      <QueryState query={squads} />{squads.data && <>
        <ul className="divide-y divide-line">{squads.data.items.map((membership) => <li className="py-4" key={membership.id}><div className="flex flex-wrap items-center justify-between gap-3">
          <Link className="font-medium text-slate-50 hover:text-emerald-200" to={`/teams/${membership.team_id}`}>{membership.team.name}</Link><Status active={membership.is_active} /></div>
          <p className="mt-1.5 text-sm text-slate-400">Shirt: {membership.shirt_number ?? 'Unassigned'} · Joined: <DateText value={membership.joined_at} />{membership.left_at && <> · Left: <DateText value={membership.left_at} /></>}</p>
        </li>)}</ul>{!squads.data.total && <p className="text-slate-400">No accessible squad memberships.</p>}<Pager total={squads.data.total} offset={offset} onChange={setOffset} />
      </>}</section>
  </>}</section>
}
