import type { UseQueryResult } from '@tanstack/react-query'
import { Activity, ChevronRight, LoaderCircle, Network, Route, RotateCw, Ruler, Workflow } from 'lucide-react'
import type { FootballMatch, Page } from '../football/types'
import { isActiveJob, JOB_LABELS, JOB_STATUS_LABELS, type ProcessingJob } from '../media/types'
import type { AnalyticsTab } from './AnalyticsTabs'
import { metric } from './format'
import { assignmentCounts, availabilityOf, resultMessage, TEAM_TONES } from './results'
import { AvailabilityBadge, Metric, MetricRow } from './ResultState'
import { TEAM_LABELS, type PlayerAnalytics, type TeamAnalytics, type TeamAssignment, type TeamTacticalSummary, type TrajectoryResult } from './types'

type AnyQuery = Pick<UseQueryResult, 'isPending' | 'isFetching' | 'error' | 'refetch'>
export interface CurrentResults {
  players?: Page<PlayerAnalytics>; tactics?: TeamAnalytics; assignments?: TeamAssignment[]; trajectories?: TrajectoryResult
}
const count = (value: number) => value.toLocaleString('en-GB')
// Shown while a result is loading or after it failed; never a zero.
const pending = (query: AnyQuery) => availabilityOf(query) === 'checking' ? 'Checking…' : 'Unavailable'

function ProcessingChip({ job }: { job: ProcessingJob | undefined }) {
  return <p className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${job
    ? 'border-sky-400/35 bg-sky-400/10 text-sky-200' : 'border-line-strong text-slate-300'}`}>
    {job ? <LoaderCircle aria-hidden="true" className="size-3.5 animate-spin motion-reduce:animate-none" /> : <Workflow aria-hidden="true" className="size-3.5 text-slate-400" />}
    {job ? `${JOB_LABELS[job.job_type]} ${JOB_STATUS_LABELS[job.status].toLowerCase()} · ${job.progress_percent}%` : 'No active processing job'}
  </p>
}

function ResultRow({ name, query, detail, tab, onOpen, assignmentsChanged = false }: {
  name: string; query: AnyQuery; detail?: string | false; tab?: [AnalyticsTab, string]; onOpen: (tab: AnalyticsTab) => void; assignmentsChanged?: boolean
}) {
  const state = availabilityOf(query)
  return <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2"><p className="font-medium text-slate-100">{name}</p><AvailabilityBadge state={state} /></div>
      {query.error ? <>
        <p className="mt-1.5 text-sm text-slate-300">{resultMessage(state, name, assignmentsChanged)}</p>
        <p className="mt-0.5 break-words text-xs text-slate-500">{query.error.message}</p>
      </> : detail && <p className="mt-1.5 text-sm text-slate-400">{detail}</p>}
    </div>
    <div className="flex shrink-0 flex-wrap gap-2">
      {(state === 'error' || state === 'denied') && <button type="button" className="button-secondary min-h-8 px-3 py-1 text-xs" onClick={() => void query.refetch()}>
        <RotateCw aria-hidden="true" className="size-3.5" />Retry</button>}
      {tab && <button type="button" className="button-secondary min-h-8 px-3 py-1 text-xs" aria-label={`Open ${tab[1]}`} onClick={() => onOpen(tab[0])}>
        Open<ChevronRight aria-hidden="true" className="-mr-1 size-3.5" /></button>}
    </div>
  </li>
}

function TeamGlance({ team }: { team: TeamTacticalSummary }) {
  return <article className="min-w-0 rounded-xl border border-line bg-canvas/40 p-5" aria-labelledby={`glance-${team.team}`}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 id={`glance-${team.team}`} className={`flex items-center gap-2 font-semibold ${TEAM_TONES[team.team].text}`}>
        <span aria-hidden="true" className={`size-2 rounded-full ${TEAM_TONES[team.team].dot}`} />{TEAM_LABELS[team.team]}</h3>
      <span className="text-xs text-slate-400">{team.valid_snapshots ? 'Geometry available' : 'Insufficient visibility'}</span>
    </div>
    <dl className="mt-2 divide-y divide-line">
      <MetricRow label="Valid snapshots" value={count(team.valid_snapshots)} hint={`${count(team.insufficient_snapshots)} insufficient snapshots excluded.`} />
      <MetricRow label="Average visible players" value={metric(team.avg_visible_players, '', 1)} />
      <MetricRow label="Average width" value={metric(team.avg_width_metres, 'm')} />
      <MetricRow label="Average depth" value={metric(team.avg_depth_metres, 'm')} />
    </dl>
  </article>
}

function PlayerGlance({ page }: { page: Page<PlayerAnalytics> }) {
  // Counts only when every track is on this page; otherwise they would be partial.
  const complete = page.offset === 0 && page.items.length === page.total
  return <article className="min-w-0 rounded-xl border border-line bg-canvas/40 p-5" aria-labelledby="glance-players">
    <h3 id="glance-players" className="flex items-center gap-2 font-semibold text-slate-100"><Activity aria-hidden="true" className="size-4 text-emerald-300" />Player tracks</h3>
    {complete ? <dl className="mt-2 divide-y divide-line">
      <MetricRow label="Partially observed" value={`${count(page.items.filter((row) => row.coverage_warning).length)} of ${count(page.total)}`}
        hint="Tracks whose observed time covers only part of the video." />
      <MetricRow label="Speed measured" value={`${count(page.items.filter((row) => row.average_speed_kmh !== null).length)} of ${count(page.total)}`}
        hint="Speeds need valid movement intervals; other tracks show Unavailable." />
      <MetricRow label="Tracks with sprints" value={`${count(page.items.filter((row) => row.sprint_count > 0).length)} of ${count(page.total)}`} />
    </dl> : <p className="mt-3 text-sm text-slate-400">Open Players to review all {count(page.total)} tracks page by page.</p>}
  </article>
}

/** Overview built only from the current saved results already loaded for the page. */
export function AnalyticsOverview({ match, jobs, queries, current, assignmentsChanged, onOpen }: {
  match: FootballMatch; jobs: ProcessingJob[]; current: CurrentResults; assignmentsChanged: boolean; onOpen: (tab: AnalyticsTab) => void
  queries: Record<'players' | 'tactics' | 'assignments' | 'trajectories', AnyQuery>
}) {
  const { players, tactics, assignments, trajectories } = current
  const counts = assignments && assignmentCounts(assignments)
  const [teamA, teamB] = (['team_a', 'team_b'] as const).map((team) => tactics?.teams.find((row) => row.team === team))
  return <>
    <section className="panel" aria-labelledby="overview-heading">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 id="overview-heading" className="text-xl font-semibold">Analysis overview</h2>
          <p className="mt-1 text-sm text-slate-400">Saved results for the current source video. Missing results stay unavailable; nothing is estimated.</p>
        </div>
        <ProcessingChip job={jobs.find(isActiveJob)} />
      </div>
      <dl className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric icon={Activity} label="Analyzed tracks" value={players ? count(players.total) : pending(queries.players)} hint="Track IDs belong to this match; they are not named players." />
        <Metric icon={Route} label="Cleaned observations" value={trajectories ? count(trajectories.usable_rows) : pending(queries.trajectories)}
          hint={trajectories ? `Of ${count(trajectories.source_rows)} mapped positions; ${count(trajectories.rejected_rows)} rejected by cleaning.` : undefined} />
        <Metric icon={Network} label="Observed frames" value={tactics ? count(tactics.summary.observed_frames) : pending(queries.tactics)}
          hint={teamA && teamB ? `Valid tactical snapshots: Team A ${count(teamA.valid_snapshots)} · Team B ${count(teamB.valid_snapshots)}.` : undefined} />
        <Metric icon={Ruler} label="Pitch dimensions" value={`${match.pitch_length_metres} × ${match.pitch_width_metres} m`} hint="X = length · Y = width" />
      </dl>
      <h3 className="mt-8 text-sm font-semibold text-slate-200">Result availability</h3>
      <ul className="mt-3 divide-y divide-line rounded-xl border border-line">
        <ResultRow name="Cleaned trajectories" query={queries.trajectories} onOpen={onOpen}
          detail={trajectories && `Result #${trajectories.job_id} · ${count(trajectories.unique_tracks)} tracks in ${count(trajectories.segments)} segments · metres`} />
        <ResultRow name="Player analytics" query={queries.players} tab={['players', 'Players']} onOpen={onOpen} detail={players && `${count(players.total)} analyzed tracks`} />
        <ResultRow name="Team tactical analytics" query={queries.tactics} tab={['tactics', 'Team Tactics']} onOpen={onOpen} assignmentsChanged={assignmentsChanged}
          detail={tactics && `Result #${tactics.job_id} · minimum ${tactics.summary.min_players_per_team} visible players per team`} />
        <ResultRow name="Team assignments" query={queries.assignments} tab={['assignments', 'Team Assignments']} onOpen={onOpen}
          detail={counts && `${count(counts.total)} tracks · Team A ${count(counts.team_a)} · Team B ${count(counts.team_b)} · Unknown ${count(counts.unknown)} · ${count(counts.manual)} manual overrides`} />
      </ul>
    </section>
    {(players || teamA || teamB) && <section className="panel" aria-labelledby="glance-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="glance-heading" className="text-xl font-semibold">At a glance</h2>
        <p className="text-sm text-slate-400">Team values are averages over valid snapshots.</p>
      </div>
      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        {players && <PlayerGlance page={players} />}
        {teamA && <TeamGlance team={teamA} />}
        {teamB && <TeamGlance team={teamB} />}
      </div>
    </section>}
  </>
}
