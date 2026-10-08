import { useState } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import type { Page } from '../football/types'
import { Field, Pager } from '../football/ui'
import { CoverageSummary } from './HeatmapPanel'
import { usePlayerDetail } from './api'
import { duration, metric } from './format'
import { Metric, ResultState, TeamBadge } from './ResultState'
import type { PlayerAnalytics, TeamAssignment } from './types'

type SortKey = 'track_id' | 'active_duration_seconds' | 'total_distance_metres' | 'average_speed_kmh' | 'max_speed_kmh' | 'sprint_count'
function sortPlayers(rows: PlayerAnalytics[], key: SortKey, descending: boolean): PlayerAnalytics[] {
  return [...rows].sort((a, b) => {
    const first = a[key], second = b[key]
    if (first === null) return second === null ? a.track_id - b.track_id : 1
    if (second === null) return -1
    return (descending ? second - first : first - second) || a.track_id - b.track_id
  })
}

export function PlayersPanel({ matchId, version, query, assignments, offset, onOffset, selected, onSelect, onHeatmap }: {
  matchId: number; version: string; query: UseQueryResult<Page<PlayerAnalytics>>; assignments: TeamAssignment[] | undefined
  offset: number; onOffset: (offset: number) => void; selected: number | null; onSelect: (id: number) => void; onHeatmap: () => void
}) {
  const [sort, setSort] = useState<SortKey>('track_id')
  const [descending, setDescending] = useState(false)
  return <div className="space-y-6">
    <section className="panel min-w-0" aria-labelledby="players-heading">
      <h2 id="players-heading" className="text-xl font-semibold">Player analytics</h2>
      <p className="mt-2 text-sm leading-6 text-slate-400">Tracks belong to this match. They are not automatically linked to named players. Sorting applies to this page only.</p>
      <ResultState query={query} name="Player analytics">{query.data && <>
        <div className="my-5 flex flex-wrap items-end gap-3">
          <Field label="Sort current page"><select className="field-input" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            <option value="track_id">Track ID</option><option value="active_duration_seconds">Active duration</option><option value="total_distance_metres">Distance</option>
            <option value="average_speed_kmh">Average speed</option><option value="max_speed_kmh">Maximum speed</option><option value="sprint_count">Sprint count</option>
          </select></Field>
          <button className="button-secondary" aria-label="Reverse sort order" onClick={() => setDescending(!descending)}>{descending ? 'Descending ↓' : 'Ascending ↑'}</button>
        </div>
        {!query.data.total ? <p className="analytics-state">No analyzed tracks are available in this result.</p> : <div className="analytics-scroll" tabIndex={0} role="region" aria-label="Player metrics table">
          <table className="analytics-table"><caption className="sr-only">Observed physical metrics by match Track ID</caption><thead><tr>
            {['Track', 'Team', 'Distance', 'Active duration', 'Average speed', 'Maximum speed', 'Sprints', 'Sprint distance'].map((label) => <th key={label} scope="col">{label}</th>)}
          </tr></thead><tbody>{sortPlayers(query.data.items, sort, descending).map((row) => <tr key={row.track_id} className={selected === row.track_id ? 'bg-emerald-950/30' : undefined}>
            <th scope="row"><button className="record-link whitespace-nowrap" aria-label={`View Track ${row.track_id}`} aria-pressed={selected === row.track_id} onClick={() => onSelect(row.track_id)}>Track {row.track_id}</button></th>
            <td><TeamBadge trackId={row.track_id} assignments={assignments} /></td><td>{metric(row.total_distance_metres, 'm')}</td>
            <td>{duration(row.active_duration_seconds)}{row.coverage_warning && <span className="mt-1 block text-xs text-amber-200" title={row.coverage_warning}>Partial observation</span>}</td><td>{metric(row.average_speed_kmh, 'km/h')}</td><td>{metric(row.max_speed_kmh, 'km/h')}</td>
            <td>{row.sprint_count}</td><td>{metric(row.sprint_distance_metres, 'm')}</td>
          </tr>)}</tbody></table>
        </div>}
        <Pager total={query.data.total} offset={offset} onChange={onOffset} />
      </>}</ResultState>
    </section>
    {selected === null ? <p className="analytics-state">Select a track to inspect its details and heatmap.</p>
      : <PlayerDetail key={`${version}:${selected}`} matchId={matchId} version={version} trackId={selected} assignments={assignments} onHeatmap={onHeatmap} />}
  </div>
}

function PlayerDetail({ matchId, version, trackId, assignments, onHeatmap }: {
  matchId: number; version: string; trackId: number; assignments: TeamAssignment[] | undefined; onHeatmap: () => void
}) {
  const query = usePlayerDetail(matchId, version, trackId)
  const row = query.data
  return <section className="panel" aria-labelledby="track-detail-heading">
    <div className="flex flex-wrap items-center justify-between gap-4"><h2 id="track-detail-heading" className="text-xl font-semibold">Track {trackId} details</h2>
      <TeamBadge trackId={trackId} assignments={assignments} /></div>
    <ResultState query={query} name="Track details">{row && <>
      <CoverageSummary observed={row.active_duration_seconds} data={row} />
      <dl className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Total distance" value={metric(row.total_distance_metres, 'm')} />
        <Metric label="Active duration" value={duration(row.active_duration_seconds)} hint="Sum of valid observed movement intervals." />
        <Metric label="Average speed" value={metric(row.average_speed_kmh, 'km/h')} /><Metric label="Maximum speed" value={metric(row.max_speed_kmh, 'km/h')} />
        <Metric label="Sprint count" value={row.sprint_count} /><Metric label="Sprint distance" value={metric(row.sprint_distance_metres, 'm')} />
        <Metric label="Sprint duration" value={metric(row.sprint_duration_seconds, 's')} /><Metric label="Segments" value={row.segment_count} />
        <Metric label="Usable observations" value={row.usable_observation_count} /><Metric label="Valid intervals" value={row.valid_interval_count} />
        <Metric label="Excluded intervals" value={row.excluded_interval_count} />
      </dl>
      <p className="mt-6 text-xs text-slate-400">Published result #{row.job_id}. Distances and speeds describe observed cleaned movement; gaps add no movement or time.</p>
      <button className="button-secondary mt-5" onClick={onHeatmap}>View Track {trackId} heatmap</button>
    </>}</ResultState>
  </section>
}
