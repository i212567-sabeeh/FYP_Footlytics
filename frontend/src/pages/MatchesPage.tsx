import { useState } from 'react'
import { CirclePlus, ListFilter } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { apiRequest } from '../api/client'
import { useRecord, useRecords } from '../features/football/api'
import { ClubPicker, TeamFilter } from '../features/football/forms'
import { MatchForm, type MatchValue } from '../features/football/MatchForm'
import { MatchHeader } from '../features/football/MatchHeader'
import { MatchRow } from '../features/football/MatchRow'
import type { FootballMatch } from '../features/football/types'
import { Empty, ErrorMessage, Field, Heading, Pager, QueryState } from '../features/football/ui'
import { useCapabilities, useSave } from '../features/football/hooks'
import { MatchMediaSections } from '../features/media/MatchMediaSections'

export function MatchesPage() {
  const [params, setParams] = useSearchParams()
  const club = params.get('club_id') ?? '', team = params.get('team_id') ?? ''
  const [format, setFormat] = useState('')
  const [archived, setArchived] = useState('false')
  const [offset, setOffset] = useState(0)
  const { match } = useCapabilities()
  const matches = useRecords<FootballMatch>('matches', { club_id: club, team_id: team, match_format: format, archived, offset, limit: 25 })
  const filtered = Boolean(club || team || format || archived !== 'false')
  function clearFilters() { setParams({}); setFormat(''); setArchived('false'); setOffset(0) }
  return <section>
    <Heading title="Matches">{match && <Link className="button-primary" to="/matches/new"><CirclePlus aria-hidden="true" className="size-4" />Create match</Link>}</Heading>
    <div className="panel mb-6 p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-medium text-slate-300"><ListFilter aria-hidden="true" className="size-4 text-slate-500" />Filters</p>
        {filtered && <button type="button" className="button-secondary min-h-8 px-3 py-1 text-xs" onClick={clearFilters}>Clear filters</button>}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <ClubPicker all value={club} onChange={(value) => { setParams(value ? { club_id: value } : {}); setOffset(0) }} />
        <TeamFilter club={club} value={team} onChange={(value) => { const next = new URLSearchParams(params); if (value) next.set('team_id', value); else next.delete('team_id'); setParams(next); setOffset(0) }} />
        <Field label="Format"><select className="field-input" value={format} onChange={(e) => { setFormat(e.target.value); setOffset(0) }}><option value="">All formats</option><option value="11v11">11v11</option><option value="5v5">5v5</option></select></Field>
        <Field label="Archive status"><select className="field-input" value={archived} onChange={(e) => { setArchived(e.target.value); setOffset(0) }}><option value="false">Current matches</option><option value="true">Archived matches</option><option value="">All matches</option></select></Field>
      </div>
    </div>
    <QueryState query={matches} />
    {matches.data && <>
      {matches.data.items.length ? <ul className="panel divide-y divide-line px-5 py-0">
        {matches.data.items.map((item) => <MatchRow key={item.id} match={item}>
          <span className="text-xs tabular-nums text-slate-400">Pitch {item.pitch_length_metres} × {item.pitch_width_metres} m</span>
        </MatchRow>)}
      </ul> : <Empty>No matches found for these filters.</Empty>}
      <Pager total={matches.data.total} offset={offset} onChange={setOffset} />
    </>}
  </section>
}
export function NewMatchPage() {
  const navigate = useNavigate()
  const save = useSave(async (data: MatchValue) => {
    const created = await apiRequest<FootballMatch>('matches', { method: 'POST', body: data })
    navigate(`/matches/${created.id}`)
  })
  return <section><Heading title="Create match" /><MatchForm saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => navigate('/matches')} /></section>
}
export function MatchDetailPage() {
  const { matchId } = useParams()
  const match = useRecord<FootballMatch>(`matches/${matchId}`)
  const [editing, setEditing] = useState(false)
  const save = useSave((data: MatchValue) => {
    const { club_id: _club, ...body } = data
    void _club
    return apiRequest(`matches/${matchId}`, { method: 'PATCH', body })
  }, () => setEditing(false))
  const archive = useSave((is_archived: boolean) => apiRequest(`matches/${matchId}`, { method: 'PATCH', body: { is_archived } }))
  return <section><QueryState query={match} />{match.data && <>
    <MatchHeader match={match.data} archiving={archive.isPending}
      onEdit={() => { save.reset(); setEditing(true) }} onArchive={() => archive.mutate(!match.data!.is_archived)} />
    <ErrorMessage error={archive.error} />
    {editing && <div className="mt-8"><MatchForm initial={match.data} saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setEditing(false)} /></div>}
    <MatchMediaSections key={match.data.id} match={match.data} />
  </>}</section>
}
