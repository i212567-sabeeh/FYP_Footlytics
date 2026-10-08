import { useState } from 'react'
import { useMutation, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { Link } from 'react-router'
import { apiRequest } from '../../api/client'
import { Field, Pager } from '../football/ui'
import { reportKey } from '../reports/api'
import { assignmentsKey, tacticsKey } from './api'
import { TeamColorsPanel } from './TeamColorsPanel'
import { metric } from './format'
import { ResultState, TeamBadge } from './ResultState'
import { TEAM_LABELS, type TeamAssignment, type TrackTeam } from './types'

function AssignmentEditor({ row, pending, save }: { row: TeamAssignment; pending: boolean; save: (id: number, team: TrackTeam | null) => void }) {
  const [team, setTeam] = useState<TrackTeam | ''>(row.manual_team ?? '')
  return <form className="flex items-end gap-2" onSubmit={(event) => { event.preventDefault(); save(row.track_id, team || null) }}>
    <Field label={`Override Track ${row.track_id}`}><select className="field-input min-w-36" value={team} disabled={pending} onChange={(event) => setTeam(event.target.value as TrackTeam | '')}>
      <option value="">Use classifier result</option><option value="team_a">Team A</option><option value="team_b">Team B</option><option value="unknown">Unknown</option>
    </select></Field>
    <button className="button-secondary" type="submit" aria-label={`Save Track ${row.track_id} override`} disabled={pending || (team || null) === row.manual_team}>Save</button>
    {row.manual_team !== null && <button className="button-secondary" type="button" aria-label={`Clear Track ${row.track_id} override`} disabled={pending} onClick={() => save(row.track_id, null)}>Clear</button>}
  </form>
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
  return <section className="panel min-w-0" aria-labelledby="assignments-heading">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="assignments-heading" className="text-xl font-semibold">Team assignment review</h2>
      <Link className="record-link text-sm" to={`/matches/${matchId}/review`}>Inspect tracked frames</Link></div>
    <p className="mt-3 text-sm leading-6 text-slate-400">Manual overrides take precedence over automatic or user-seeded jersey classification. Unknown tracks contribute to neither team's geometry. Save a choice intentionally; Clear restores the classifier result.</p>
    <button className="button-secondary mt-4" aria-expanded={colorsOpen} onClick={() => setColorsOpen(!colorsOpen)}>{colorsOpen ? 'Close team colors' : 'Set Team Colors'}</button>
    {colorsOpen && <TeamColorsPanel matchId={matchId} canManage={canManage} />}
    {!canManage && <p className="mt-3 text-sm text-slate-300">Read-only assignment review.</p>}
    {action.isPending && <p className="mt-4 text-sm text-sky-200" role="status">Saving Track {action.variables.trackId} assignment…</p>}
    {action.isSuccess && <p className="mt-4 text-sm text-emerald-300" role="status">Saved Track {action.data.track_id} assignment. Effective team: {TEAM_LABELS[action.data.effective_team]}.</p>}
    {action.error && <p className="mt-4 text-sm text-red-300" role="alert">Assignment was not saved. {action.error.message}</p>}
    <ResultState query={query} name="Team assignments">{query.data && <>
      {!query.data.length ? <p className="analytics-state">No current team assignments are available. Complete team classification before reviewing assignments.</p>
        : <div className="analytics-scroll mt-5" tabIndex={0} role="region" aria-label="Team assignment table"><table className="analytics-table">
          <caption className="sr-only">Classifier evidence, manual corrections and effective track teams</caption><thead><tr>
            {['Track', 'Classifier team', 'Evidence confidence', 'Classification source', 'Manual override', 'Effective team', ...(canManage ? ['Correction'] : [])].map((label) => <th scope="col" key={label}>{label}</th>)}
          </tr></thead><tbody>{query.data.slice(offset, offset + 25).map((row) => <tr key={row.track_id}>
            <th scope="row">Track {row.track_id}</th><td>{TEAM_LABELS[row.automatic_team]}</td><td>{metric(row.automatic_confidence * 100, '%')}</td>
            <td><span>{row.classification_mode === 'user_seeded' ? 'User-seeded' : 'Automatic'}</span>{row.classification_provenance?.rejection_reason && <p className="mt-1 max-w-48 text-xs text-slate-400">{row.classification_provenance.rejection_reason.replaceAll('_', ' ')}</p>}</td>
            <td>{row.manual_team === null ? 'None — classifier' : `Manual: ${TEAM_LABELS[row.manual_team]}`}</td>
            <td><TeamBadge trackId={row.track_id} assignments={query.data} /></td>
            {canManage && <td><AssignmentEditor key={`${row.track_id}:${row.manual_team}:${row.updated_at}`} row={row} pending={action.isPending} save={(trackId, team) => action.mutate({ trackId, team })} /></td>}
          </tr>)}</tbody></table></div>}
      <Pager total={query.data.length} offset={offset} onChange={setOffset} />
    </>}</ResultState>
  </section>
}
