import { useRef, type ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { Activity, ArrowDownWideNarrow, ArrowUpNarrowWide, Flame, Footprints, ListChecks, MousePointerClick, TriangleAlert, Zap, type LucideIcon } from 'lucide-react'
import type { Page } from '../football/types'
import { Field, Pager } from '../football/ui'
import { CoverageSummary } from './HeatmapPanel'
import { usePlayerDetail } from './api'
import { duration, metric } from './format'
import { Metric, ResultState, TeamBadge } from './ResultState'
import type { PlayerAnalytics, TeamAssignment } from './types'

export type SortKey = 'track_id' | 'active_duration_seconds' | 'total_distance_metres' | 'average_speed_kmh' | 'max_speed_kmh' | 'sprint_count'
export interface PlayerSort { key: SortKey; descending: boolean }
function sortPlayers(rows: PlayerAnalytics[], { key, descending }: PlayerSort): PlayerAnalytics[] {
  return [...rows].sort((a, b) => {
    const first = a[key], second = b[key]
    if (first === null) return second === null ? a.track_id - b.track_id : 1
    if (second === null) return -1
    return (descending ? second - first : first - second) || a.track_id - b.track_id
  })
}
const COLUMNS = ['Track', 'Team', 'Distance', 'Active duration', 'Average speed', 'Maximum speed', 'Sprints', 'Sprint distance'] as const

/** Missing values stay visibly Unavailable, muted so measured values stand out. */
function Value({ text }: { text: string }) {
  return text === 'Unavailable' ? <span className="text-slate-500">{text}</span> : <>{text}</>
}

export function PlayersPanel({ matchId, version, query, assignments, offset, onOffset, selected, onSelect, onHeatmap, sort, onSort }: {
  matchId: number; version: string; query: UseQueryResult<Page<PlayerAnalytics>>; assignments: TeamAssignment[] | undefined
  offset: number; onOffset: (offset: number) => void; selected: number | null; onSelect: (id: number) => void; onHeatmap: () => void
  sort: PlayerSort; onSort: (sort: PlayerSort) => void
}) {
  const detail = useRef<HTMLDivElement>(null)
  function select(trackId: number) {
    onSelect(trackId)
    // The details sit below the table; bring them into view when they start off screen.
    window.setTimeout(() => {
      const element = detail.current
      const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      if (element && element.getBoundingClientRect().top > window.innerHeight - 160) element.scrollIntoView?.({ block: 'start', behavior: still ? 'auto' : 'smooth' })
    }, 0)
  }
  return <div className="space-y-6">
    <section className="panel min-w-0" aria-labelledby="players-heading">
      <h2 id="players-heading" className="flex items-center gap-2 text-xl font-semibold"><Activity aria-hidden="true" className="size-5 text-emerald-300" />Player analytics</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Tracks belong to this match. They are not automatically linked to named players. Sorting applies to this page only.</p>
      <ResultState query={query} name="Player analytics">{query.data && <>
        <div className="mt-5 flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Sort current page"><select className="field-input" value={sort.key} onChange={(e) => onSort({ ...sort, key: e.target.value as SortKey })}>
              <option value="track_id">Track ID</option><option value="active_duration_seconds">Active duration</option><option value="total_distance_metres">Distance</option>
              <option value="average_speed_kmh">Average speed</option><option value="max_speed_kmh">Maximum speed</option><option value="sprint_count">Sprint count</option>
            </select></Field>
            <button className="button-secondary" aria-label="Reverse sort order" onClick={() => onSort({ ...sort, descending: !sort.descending })}>
              {sort.descending ? <ArrowDownWideNarrow aria-hidden="true" className="size-4" /> : <ArrowUpNarrowWide aria-hidden="true" className="size-4" />}
              {sort.descending ? 'Descending' : 'Ascending'}</button>
          </div>
          <p className="flex items-center gap-2 text-xs text-slate-400"><MousePointerClick aria-hidden="true" className="size-4 text-slate-500" />Select a track for details and its heatmap.</p>
        </div>
        {query.data.total > 0 && <p className="mt-3 text-xs text-slate-500 xl:hidden">Scroll the table sideways to see every metric; the Track column stays visible.</p>}
        {!query.data.total ? <p className="analytics-state">No analyzed tracks are available in this result.</p> : <div className="analytics-scroll mt-4" tabIndex={0} role="region" aria-label="Player metrics table">
          <table className="analytics-table"><caption className="sr-only">Observed physical metrics by match Track ID</caption><thead><tr>
            {COLUMNS.map((label, index) => <th key={label} scope="col" className={index === 0 ? 'sticky left-0 z-10 bg-canvas' : index > 1 ? 'text-right' : undefined}>{label}</th>)}
          </tr></thead><tbody>{sortPlayers(query.data.items, sort).map((row) => {
            const active = selected === row.track_id
            return <tr key={row.track_id} className={`group ${active ? 'bg-surface-raised' : ''}`}>
              <th scope="row" className={`sticky left-0 z-10 ${active ? 'bg-surface-raised shadow-[inset_3px_0_0_var(--color-brand)]' : 'bg-surface group-hover:bg-surface-raised'}`}>
                <button className={`inline-flex items-center gap-2 whitespace-nowrap rounded font-medium underline-offset-4 hover:underline ${active ? 'text-emerald-200' : 'text-emerald-300'}`}
                  aria-label={`View Track ${row.track_id}`} aria-pressed={active} onClick={() => select(row.track_id)}>Track {row.track_id}</button>
              </th>
              <td><TeamBadge trackId={row.track_id} assignments={assignments} /></td>
              <td className="text-right"><Value text={metric(row.total_distance_metres, 'm')} /></td>
              <td className="text-right"><Value text={duration(row.active_duration_seconds)} />{row.coverage_warning && <span className="mt-1 flex items-center justify-end gap-1 text-xs text-amber-200" title={row.coverage_warning}>
                <TriangleAlert aria-hidden="true" className="size-3 shrink-0" />Partial observation</span>}</td>
              <td className="text-right"><Value text={metric(row.average_speed_kmh, 'km/h')} /></td>
              <td className="text-right"><Value text={metric(row.max_speed_kmh, 'km/h')} /></td>
              <td className="text-right">{row.sprint_count}</td>
              <td className="text-right"><Value text={metric(row.sprint_distance_metres, 'm')} /></td>
            </tr>
          })}</tbody></table>
        </div>}
        <Pager total={query.data.total} offset={offset} onChange={onOffset} />
      </>}</ResultState>
    </section>
    <div ref={detail} className="scroll-mt-36">
      {selected === null ? <p className="analytics-state mt-0 flex items-center gap-3"><MousePointerClick aria-hidden="true" className="size-5 shrink-0 text-slate-500" />Select a track to inspect its details and heatmap.</p>
        : <PlayerDetail key={`${version}:${selected}`} matchId={matchId} version={version} trackId={selected} assignments={assignments} onHeatmap={onHeatmap} />}
    </div>
  </div>
}

function MetricGroup({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: ReactNode }) {
  return <div className="mt-6">
    <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400"><Icon aria-hidden="true" className="size-4 text-slate-500" />{title}</h3>
    <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{children}</dl>
  </div>
}

function PlayerDetail({ matchId, version, trackId, assignments, onHeatmap }: {
  matchId: number; version: string; trackId: number; assignments: TeamAssignment[] | undefined; onHeatmap: () => void
}) {
  const query = usePlayerDetail(matchId, version, trackId)
  const row = query.data
  return <section className="panel" aria-labelledby="track-detail-heading">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex min-w-0 items-center gap-3">
        <span aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-full bg-canvas text-sm font-semibold tabular-nums text-emerald-200 ring-2 ring-emerald-400/40">{trackId}</span>
        <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Selected track</p>
          <h2 id="track-detail-heading" className="text-xl font-semibold">Track {trackId} details</h2></div>
      </div>
      <TeamBadge trackId={trackId} assignments={assignments} />
    </div>
    <ResultState query={query} name="Track details">{row && <>
      <div className="mt-5 flex flex-col gap-3 rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-slate-300">Published result #{row.job_id}. Distances and speeds describe observed cleaned movement; gaps add no movement or time.</p>
        <button className="button-primary shrink-0" onClick={onHeatmap}><Flame aria-hidden="true" className="size-4" />View Track {trackId} heatmap</button>
      </div>
      <CoverageSummary observed={row.active_duration_seconds} data={row} />
      <MetricGroup title="Movement" icon={Footprints}>
        <Metric label="Total distance" value={metric(row.total_distance_metres, 'm')} />
        <Metric label="Active duration" value={duration(row.active_duration_seconds)} hint="Sum of valid observed movement intervals." />
        <Metric label="Average speed" value={metric(row.average_speed_kmh, 'km/h')} /><Metric label="Maximum speed" value={metric(row.max_speed_kmh, 'km/h')} />
      </MetricGroup>
      <MetricGroup title="Sprints" icon={Zap}>
        <Metric label="Sprint count" value={row.sprint_count} /><Metric label="Sprint distance" value={metric(row.sprint_distance_metres, 'm')} />
        <Metric label="Sprint duration" value={metric(row.sprint_duration_seconds, 's')} />
      </MetricGroup>
      <MetricGroup title="Observation quality" icon={ListChecks}>
        <Metric label="Segments" value={row.segment_count} /><Metric label="Usable observations" value={row.usable_observation_count} />
        <Metric label="Valid intervals" value={row.valid_interval_count} /><Metric label="Excluded intervals" value={row.excluded_interval_count} />
      </MetricGroup>
    </>}</ResultState>
  </section>
}
