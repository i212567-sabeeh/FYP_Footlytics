import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { apiRequest } from '../api/client'
import { useRecord, useRecords } from '../features/football/api'
import { ClubPicker, TeamFilter } from '../features/football/forms'
import { MatchForm, type MatchValue } from '../features/football/MatchForm'
import type { FootballMatch } from '../features/football/types'
import { DateText, Empty, ErrorMessage, Field, Heading, Pager, QueryState } from '../features/football/ui'
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
  return <section><Heading title="Matches">{match && <Link className="button-primary" to="/matches/new">Create match</Link>}</Heading>
    <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><ClubPicker all value={club} onChange={(value) => { setParams(value ? { club_id: value } : {}); setOffset(0) }} />
      <TeamFilter club={club} value={team} onChange={(value) => { const next = new URLSearchParams(params); if (value) next.set('team_id', value); else next.delete('team_id'); setParams(next); setOffset(0) }} />
      <Field label="Format"><select className="field-input" value={format} onChange={(e) => { setFormat(e.target.value); setOffset(0) }}><option value="">All formats</option><option value="11v11">11v11</option><option value="5v5">5v5</option></select></Field>
      <Field label="Archive status"><select className="field-input" value={archived} onChange={(e) => { setArchived(e.target.value); setOffset(0) }}><option value="false">Current matches</option><option value="true">Archived matches</option><option value="">All matches</option></select></Field>
    </div><QueryState query={matches} />{matches.data && <><div className="space-y-4">{matches.data.items.map((item) => <article className="panel" key={item.id}>
      <div className="flex flex-wrap justify-between gap-4"><Link className="record-link text-lg" to={`/matches/${item.id}`}>{item.title}</Link><span className="text-sm text-slate-400">{item.match_format}{item.is_archived && ' · Archived'}</span></div>
      <p className="mt-3">{item.team_a.name} <span className="text-slate-500">vs</span> {item.team_b.name}</p>
      <p className="mt-2 text-sm text-slate-400">{item.club.name} · <DateText value={item.match_date} /> · {item.pitch_length_metres} × {item.pitch_width_metres} m</p>
    </article>)}</div>{!matches.data.total && <Empty>No matches found for these filters.</Empty>}<Pager total={matches.data.total} offset={offset} onChange={setOffset} /></>}
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
  const capability = useCapabilities()
  const save = useSave((data: MatchValue) => {
    const { club_id: _club, ...body } = data
    void _club
    return apiRequest(`matches/${matchId}`, { method: 'PATCH', body })
  }, () => setEditing(false))
  const archive = useSave((is_archived: boolean) => apiRequest(`matches/${matchId}`, { method: 'PATCH', body: { is_archived } }))
  return <section><Link className="record-link" to="/matches">All matches</Link><QueryState query={match} />{match.data && <>
    <div className="mt-6"><Heading title={match.data.title}>{capability.match && match.data.club.is_active && <div className="flex gap-3"><button className="button-secondary" onClick={() => { save.reset(); setEditing(true) }}>Edit match</button>
      <button className="button-secondary" disabled={archive.isPending} onClick={() => archive.mutate(!match.data!.is_archived)}>{match.data.is_archived ? 'Restore match' : 'Archive match'}</button></div>}</Heading></div>
    <ErrorMessage error={archive.error} />{editing && <MatchForm initial={match.data} saving={save.isPending} error={save.error} onSave={save.mutate} onCancel={() => setEditing(false)} />}
    <div className="panel"><p className="mb-2 text-sm font-semibold uppercase tracking-widest text-emerald-400">{match.data.match_format}{match.data.is_archived && ' · Archived'}</p>
      <h2 className="text-2xl">{match.data.team_a.name} <span className="text-slate-500">vs</span> {match.data.team_b.name}</h2>
      <dl className="mt-6 grid gap-6 sm:grid-cols-2">
        <div><dt className="text-sm text-slate-500">Club</dt><dd><Link className="record-link" to={`/clubs/${match.data.club_id}`}>{match.data.club.name}</Link></dd></div>
        <div><dt className="text-sm text-slate-500">Match date (local)</dt><dd><DateText value={match.data.match_date} /></dd></div>
        <div><dt className="text-sm text-slate-500">Pitch dimensions</dt><dd>{match.data.pitch_length_metres} m length (X) × {match.data.pitch_width_metres} m width (Y)</dd></div>
        <div><dt className="text-sm text-slate-500">Venue</dt><dd>{match.data.venue || 'Not recorded'}</dd></div>
        <div><dt className="text-sm text-slate-500">Created by</dt><dd>{match.data.created_by.full_name}</dd></div>
        <div><dt className="text-sm text-slate-500">Notes</dt><dd className="whitespace-pre-wrap">{match.data.notes || 'No notes recorded.'}</dd></div>
      </dl>
    </div><MatchMediaSections key={match.data.id} match={match.data} />{capability.analytics && !match.error && <section className="panel mt-8"><h2 className="text-xl font-semibold">Match analytics</h2><p className="mt-3 text-slate-400">Inspect observed player movement, heatmaps, team geometry and track assignments.</p><Link className="button-primary mt-5 inline-block" to={`/matches/${match.data.id}/analytics`}>View Analytics</Link></section>}
  </>}</section>
}
