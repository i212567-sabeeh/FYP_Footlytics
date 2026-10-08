import { useId, useState } from 'react'
import { useMutation, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { Palette, ScanSearch, Tags } from 'lucide-react'
import { Link } from 'react-router'
import { apiRequest } from '../../api/client'
import { Pager } from '../football/ui'
import { reportKey } from '../reports/api'
import { assignmentsKey, tacticsKey } from './api'
import { TeamColorsPanel } from './TeamColorsPanel'
import { metric } from './format'
import { assignmentCounts, TEAM_TONES } from './results'
import { ResultState, TeamBadge } from './ResultState'
import { TEAM_LABELS, type TeamAssignment, type TrackTeam } from './types'

function AssignmentEditor({ row, pending, save }: { row: TeamAssignment; pending: boolean; save: (id: number, team: TrackTeam | null) => void }) {
  const id = useId()
  const [team, setTeam] = useState<TrackTeam | ''>(row.manual_team ?? '')
  // The Track column and Correction header label the row visually; the select keeps its own name.
  return <form className="flex items-center gap-2" onSubmit={(event) => { event.preventDefault(); save(row.track_id, team || null) }}>
    <label className="sr-only" htmlFor={id}>{`Override Track ${row.track_id}`}</label>
    <select id={id} className="field-input min-w-40 py-1.5" value={team} disabled={pending} onChange={(event) => setTeam(event.target.value as TrackTeam | '')}>
      <option value="">Use classifier result</option><option value="team_a">Team A</option><option value="team_b">Team B</option><option value="unknown">Unknown</option>
    </select>
    <button className="button-secondary min-h-9 px-3 py-1.5" type="submit" aria-label={`Save Track ${row.track_id} override`} disabled={pending || (team || null) === row.manual_team}>Save</button>
    {row.manual_team !== null && <button className="button-secondary min-h-9 px-3 py-1.5" type="button" aria-label={`Clear Track ${row.track_id} override`} disabled={pending} onClick={() => save(row.track_id, null)}>Clear</button>}
  </form>
}

function Confidence({ value }: { value: number }) {
  const percent = Math.min(100, Math.max(0, value * 100))
  return <div className="flex items-center justify-end gap-3">
    <span aria-hidden="true" className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-800"><span className="block h-full rounded-full bg-emerald-400/70" style={{ width: `${percent}%` }} /></span>
    <span>{metric(value * 100, '%')}</span>
  </div>
}

export function AssignmentsPanel({ matchId, query, canManage, onChanged }: {
  matchId: number; query: UseQueryResult<TeamAssignment[]>; canManage: boolean; onChanged: () => void
}) {
  const client = useQueryClient()
  const [offset, setOffset] = useState(0)
  const [colorsOpen, setColorsOpen] = useState(false)
  const action = useMutation({
    mutationFn: ({ trackId, team }: { trackId: number; team: TrackTeam | null }) => apiRequest<TeamAssignment>(
      `matches/${matchId}/tracks/${trackId}/team`, { method: 'PATCH', body: { team } }),
    onSuccess: () => {
      onChanged()
      // Reset discards old tactics immediately, including in-flight series pages.
      // Physical analytics deliberately use a different query prefix.
      return Promise.all([
        client.resetQueries({ queryKey: assignmentsKey(matchId) }),
        client.resetQueries({ queryKey: tacticsKey(matchId) }),
        client.resetQueries({ queryKey: reportKey(matchId) }),
      ])
    },
  })
  const counts = query.data && assignmentCounts(query.data)
  return <section className="panel min-w-0" aria-labelledby="assignments-heading">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 max-w-3xl">
        <h2 id="assignments-heading" className="flex items-center gap-2 text-xl font-semibold"><Tags aria-hidden="true" className="size-5 text-emerald-300" />Team assignment review</h2>
        <p className="mt-2 text-sm leading-6 text-slate-400">Manual overrides take precedence over automatic or user-seeded jersey classification. Unknown tracks contribute to neither team's geometry. Save a choice intentionally; Clear restores the classifier result.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link className="button-secondary" to={`/matches/${matchId}/review`}><ScanSearch aria-hidden="true" className="size-4" />Inspect tracked frames</Link>
        <button className="button-secondary" aria-expanded={colorsOpen} onClick={() => setColorsOpen(!colorsOpen)}><Palette aria-hidden="true" className="size-4" />{colorsOpen ? 'Close team colors' : 'Set Team Colors'}</button>
      </div>
    </div>
    {colorsOpen && <TeamColorsPanel matchId={matchId} canManage={canManage} />}
    {!canManage && <p className="mt-4 rounded-lg border border-line bg-canvas/40 px-3 py-2 text-sm text-slate-300">Read-only assignment review.</p>}
    {action.isPending && <p className="mt-4 text-sm text-sky-200" role="status">Saving Track {action.variables.trackId} assignment…</p>}
    {action.isSuccess && <p className="mt-4 text-sm text-emerald-300" role="status">Saved Track {action.data.track_id} assignment. Effective team: {TEAM_LABELS[action.data.effective_team]}.</p>}
    {action.error && <p className="mt-4 text-sm text-red-300" role="alert">Assignment was not saved. {action.error.message}</p>}
    <ResultState query={query} name="Team assignments">{query.data && <>
      {counts && counts.total > 0 && <ul className="mt-5 flex flex-wrap gap-2 text-xs font-medium" aria-label="Effective team counts">
        {(['team_a', 'team_b', 'unknown'] as const).map((team) => <li key={team} className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 ${TEAM_TONES[team].badge}`}>
          <span aria-hidden="true" className={`size-1.5 rounded-full ${TEAM_TONES[team].dot}`} /><span>{TEAM_LABELS[team]}</span><span className="tabular-nums">{counts[team]}</span></li>)}
        <li className="inline-flex items-center gap-2 rounded-full border border-line-strong px-3 py-1.5 text-slate-300"><span>Manual overrides</span><span className="tabular-nums">{counts.manual}</span></li>
      </ul>}
      {!query.data.length ? <p className="analytics-state">No current team assignments are available. Complete team classification before reviewing assignments.</p> : <>
        {canManage && <p className="mt-4 text-xs text-slate-500 2xl:hidden">Scroll the table sideways to reach the correction controls; the Track column stays visible.</p>}
        <div className="analytics-scroll mt-3" tabIndex={0} role="region" aria-label="Team assignment table"><table className="analytics-table">
          <caption className="sr-only">Classifier evidence, manual corrections and effective track teams</caption><thead><tr>
            {['Track', 'Classifier team', 'Evidence confidence', 'Classification source', 'Manual override', 'Effective team', ...(canManage ? ['Correction'] : [])].map((label, index) =>
              <th scope="col" key={label} className={index === 0 ? 'sticky left-0 z-10 bg-canvas' : label === 'Evidence confidence' ? 'text-right' : undefined}>{label}</th>)}
          </tr></thead><tbody>{query.data.slice(offset, offset + 25).map((row) => <tr key={row.track_id} className="group">
            <th scope="row" className="sticky left-0 z-10 bg-surface group-hover:bg-surface-raised">Track {row.track_id}</th><td>{TEAM_LABELS[row.automatic_team]}</td><td className="text-right"><Confidence value={row.automatic_confidence} /></td>
            <td><span>{row.classification_mode === 'user_seeded' ? 'User-seeded' : 'Automatic'}</span>{row.classification_provenance?.rejection_reason && <p className="mt-1 max-w-48 whitespace-normal text-xs text-slate-400">{row.classification_provenance.rejection_reason.replaceAll('_', ' ')}</p>}</td>
            <td className={row.manual_team === null ? 'text-slate-400' : 'text-slate-100'}>{row.manual_team === null ? 'None — classifier' : `Manual: ${TEAM_LABELS[row.manual_team]}`}</td>
            <td><TeamBadge trackId={row.track_id} assignments={query.data} /></td>
            {canManage && <td><AssignmentEditor key={`${row.track_id}:${row.manual_team}:${row.updated_at}`} row={row} pending={action.isPending} save={(trackId, team) => action.mutate({ trackId, team })} /></td>}
          </tr>)}</tbody></table></div>
      </>}
      <Pager total={query.data.length} offset={offset} onChange={setOffset} />
    </>}</ResultState>
  </section>
}
