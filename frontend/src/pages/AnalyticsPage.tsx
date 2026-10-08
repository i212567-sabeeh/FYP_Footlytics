import { useRef, useState } from 'react'
import { useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { ApiError } from '../api/client'
import { AnalyticsJobs } from '../features/analytics/AnalyticsJobs'
import { AssignmentsPanel } from '../features/analytics/AssignmentsPanel'
import { HeatmapPanel } from '../features/analytics/HeatmapPanel'
import { PlayersPanel } from '../features/analytics/PlayersPanel'
import { Metric, ResultState } from '../features/analytics/ResultState'
import { TeamTacticsPanel } from '../features/analytics/TeamTacticsPanel'
import { jobVersion, useAssignments, usePlayerAnalytics, useTeamAnalytics, useTrajectoryResult } from '../features/analytics/api'
import { TEAM_LABELS } from '../features/analytics/types'
import { useRecord } from '../features/football/api'
import { useCapabilities } from '../features/football/hooks'
import type { FootballMatch } from '../features/football/types'
import { Heading, QueryState } from '../features/football/ui'
import { mediaKey, useMatchJobs, useMatchVideo } from '../features/media/api'
import { isActiveJob, type MatchVideo, type ProcessingJob } from '../features/media/types'
import { ReportsPanel } from '../features/reports/ReportsPanel'

const TABS = [
  ['overview', 'Overview'], ['players', 'Players'], ['tactics', 'Team Tactics'], ['heatmap', 'Heatmap'], ['assignments', 'Team Assignments'],
] as const
type Tab = typeof TABS[number][0]
const UPSTREAM = ['video_preparation', 'player_detection', 'player_tracking', 'coordinate_mapping', 'trajectory_cleaning'] as const

function availability(query: Pick<UseQueryResult, 'isPending' | 'isFetching' | 'error'>): string {
  if (query.error) return query.error instanceof ApiError && /stale|changed|replaced/i.test(query.error.message) ? 'Regeneration needed' : 'Unavailable'
  return query.isPending || query.isFetching ? 'Checking…' : 'Available'
}

function AnalyticsContent({ match, video, jobs }: { match: FootballMatch; video: MatchVideo; jobs: ProcessingJob[] }) {
  const [tab, setTab] = useState<Tab>('overview')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [assignmentsChanged, setAssignmentsChanged] = useState(false)
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  const capability = useCapabilities()
  const base = `${video.id}:${video.updated_at}:${match.pitch_length_metres}:${match.pitch_width_metres}`
  const playerVersion = `${base}:${jobVersion(jobs, [...UPSTREAM, 'player_analytics'])}`
  const tacticalVersion = `${base}:${jobVersion(jobs, [...UPSTREAM, 'team_classification', 'team_tactical_analytics'])}`
  const assignmentVersion = `${base}:${jobVersion(jobs, ['player_detection', 'player_tracking', 'team_classification'])}`
  const players = usePlayerAnalytics(match.id, playerVersion, offset)
  const tactics = useTeamAnalytics(match.id, tacticalVersion)
  const assignments = useAssignments(match.id, assignmentVersion)
  const trajectories = useTrajectoryResult(match.id, `${base}:${jobVersion(jobs, UPSTREAM)}`)
  const canManage = capability.match && match.club.is_active && !match.is_archived
  const currentAssignments = assignments.isSuccess && !assignments.isFetching ? assignments.data : undefined
  const currentPlayers = players.isSuccess && !players.isFetching ? players.data : undefined
  const currentTactics = tactics.isSuccess && !tactics.isFetching ? tactics.data : undefined
  const trajectoryReady = trajectories.isSuccess && !trajectories.isFetching && trajectories.data.video_id === video.id

  return <div className="mt-7 min-w-0">
    <div className="flex flex-wrap gap-1 border-b border-slate-800 pb-3" role="tablist" aria-label="Match analytics sections">
      {TABS.map(([key, label], index) => <button key={key} id={`analytics-tab-${key}`} type="button" role="tab" aria-selected={tab === key}
        aria-controls={`analytics-panel-${key}`} tabIndex={tab === key ? 0 : -1} ref={(element) => { tabs.current[index] = element }}
        className={`rounded-lg px-3 py-2.5 text-sm font-medium ${tab === key ? 'bg-emerald-400 text-slate-950' : 'text-slate-300 hover:bg-slate-900'}`}
        onClick={() => setTab(key)} onKeyDown={(event) => {
          const next = event.key === 'ArrowRight' ? (index + 1) % TABS.length : event.key === 'ArrowLeft' ? (index + TABS.length - 1) % TABS.length
            : event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length - 1 : null
          if (next === null) return
          event.preventDefault(); setTab(TABS[next]![0]); tabs.current[next]?.focus()
        }}>{label}</button>)}
    </div>
    <div className="mt-6 min-w-0 space-y-6" role="tabpanel" id={`analytics-panel-${tab}`} aria-labelledby={`analytics-tab-${tab}`}>
      {tab === 'overview' && <>
        <section className="panel" aria-labelledby="overview-heading"><h2 id="overview-heading" className="text-xl font-semibold">Analysis overview</h2>
          <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-7 lg:grid-cols-4">
            <Metric label="Pitch dimensions" value={`${match.pitch_length_metres} × ${match.pitch_width_metres} m`} hint="X = length · Y = width" />
            <Metric label="Analyzed tracks" value={currentPlayers?.total ?? 'Unavailable'} />
            <Metric label="Processing" value={jobs.some(isActiveJob) ? 'In progress' : 'No active job'} />
            <Metric label="Source video" value={video.original_filename} />
            <Metric label="Cleaned trajectories" value={availability(trajectories)} />
            <Metric label="Player analytics" value={availability(players)} />
            <Metric label="Team tactical analytics" value={availability(tactics)} />
            <Metric label="Team assignments" value={availability(assignments)} />
          </dl>
          <div className="mt-6 grid gap-3 border-t border-slate-800 pt-5 sm:grid-cols-2">{(['team_a', 'team_b'] as const).map((team) => {
            const summary = currentTactics?.teams.find((row) => row.team === team)
            return <p key={team} className="text-sm text-slate-300"><strong>{TEAM_LABELS[team]}</strong>: {summary ? summary.valid_snapshots ? `${summary.valid_snapshots} valid tactical snapshots` : 'Insufficient visible players' : 'Tactical result unavailable'}</p>
          })}</div>
        </section>
        <ResultState query={trajectories} name="Cleaned trajectories">{trajectories.data && <p className="text-sm text-slate-400">Trajectory result #{trajectories.data.job_id}: {trajectories.data.usable_rows} usable observations across {trajectories.data.unique_tracks} tracks. Metrics use cleaned positions only.</p>}</ResultState>
        <ResultState query={players} name="Player analytics" />
        <ResultState query={tactics} name="Team tactical analytics" assignmentsChanged={assignmentsChanged} />
        <ReportsPanel matchId={match.id} version={`${match.updated_at}:${playerVersion}:${tacticalVersion}:${assignmentVersion}`} jobs={jobs} canManage={canManage} playersReady={!!currentPlayers} teamsReady={!!currentTactics} />
      </>}
      {tab === 'players' && <PlayersPanel matchId={match.id} version={playerVersion} query={players} assignments={currentAssignments}
        offset={offset} onOffset={setOffset} selected={selected} onSelect={setSelected} onHeatmap={() => setTab('heatmap')} />}
      {tab === 'heatmap' && <HeatmapPanel key={selected ?? 'none'} matchId={match.id} version={playerVersion} selected={selected} assignments={currentAssignments} onSelect={setSelected} />}
      {tab === 'tactics' && <TeamTacticsPanel matchId={match.id} version={tacticalVersion} query={tactics} assignmentsChanged={assignmentsChanged} />}
      {tab === 'assignments' && <AssignmentsPanel matchId={match.id} query={assignments} canManage={canManage} onChanged={() => setAssignmentsChanged(true)} />}
      {(tab === 'overview' || tab === 'tactics' || tab === 'players') && <AnalyticsJobs matchId={match.id} jobs={jobs} canManage={canManage}
        trajectoriesReady={trajectoryReady} assignmentsReady={!!currentAssignments && (currentAssignments.length > 0 || trajectories.data?.unique_tracks === 0)} />}
    </div>
  </div>
}

function Dashboard({ match }: { match: FootballMatch }) {
  const client = useQueryClient()
  const video = useMatchVideo(match.id)
  const jobs = useMatchJobs(match.id, 0, true)
  const currentVideo = video.data
  return <>
    <div className="flex flex-wrap items-center justify-between gap-4"><div>
      <p className="text-lg font-medium text-slate-200">{match.title}</p>
      <p className="mt-2 text-sm text-slate-400">{match.team_a.name} vs {match.team_b.name} · {match.match_format} · {match.club.name}</p>
    </div><button className="button-secondary" onClick={() => void client.resetQueries({ queryKey: mediaKey(match.id) })}>Refresh analytics</button></div>
    <QueryState query={video} /><QueryState query={jobs} />
    {video.isSuccess && !video.data && <p className="analytics-state">Upload a valid match video and complete processing before viewing analytics.</p>}
    {currentVideo && !video.error && jobs.isSuccess && !jobs.error && <AnalyticsContent key={`${match.id}:${currentVideo.id}`} match={match} video={currentVideo} jobs={jobs.data.items.filter((job) => job.video_id === currentVideo.id)} />}
  </>
}

export function AnalyticsPage() {
  const { matchId } = useParams()
  const match = useRecord<FootballMatch>(`matches/${matchId}`)
  return <section className="min-w-0">
    <Link className="record-link text-sm" to={`/matches/${matchId}`}>Back to Match Details</Link>
    <div className="mt-6"><Heading title="Match Analytics" /></div>
    <QueryState query={match} />
    {match.data && !match.error && <Dashboard key={match.data.id} match={match.data} />}
  </section>
}
