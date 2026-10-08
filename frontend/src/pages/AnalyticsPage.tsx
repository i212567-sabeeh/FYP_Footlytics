import { useEffect, useRef, useState } from 'react'
import { useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { ArrowLeft, CalendarDays, ChartColumnBig, RefreshCw, Shield, Video, VideoOff } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { AnalyticsJobs } from '../features/analytics/AnalyticsJobs'
import { AnalyticsOverview } from '../features/analytics/AnalyticsOverview'
import { AnalyticsTabs, type AnalyticsTab } from '../features/analytics/AnalyticsTabs'
import { AssignmentsPanel } from '../features/analytics/AssignmentsPanel'
import { HeatmapPanel } from '../features/analytics/HeatmapPanel'
import { PlayersPanel, type PlayerSort } from '../features/analytics/PlayersPanel'
import { TeamTacticsPanel } from '../features/analytics/TeamTacticsPanel'
import { jobVersion, useAssignments, usePlayerAnalytics, useTeamAnalytics, useTrajectoryResult } from '../features/analytics/api'
import { availabilityOf } from '../features/analytics/results'
import { useRecord } from '../features/football/api'
import { useCapabilities } from '../features/football/hooks'
import type { FootballMatch } from '../features/football/types'
import { QueryState } from '../features/football/ui'
import { mediaKey, useMatchJobs, useMatchVideo } from '../features/media/api'
import type { MatchVideo, ProcessingJob } from '../features/media/types'
import { ReportsPanel } from '../features/reports/ReportsPanel'

const UPSTREAM = ['video_preparation', 'player_detection', 'player_tracking', 'coordinate_mapping', 'trajectory_cleaning'] as const
// Sticky top bar (4rem) plus the sticky tab bar; matches the panel's scroll-mt-32.
const STICKY_OFFSET = 128

function AnalyticsContent({ match, video, jobs }: { match: FootballMatch; video: MatchVideo; jobs: ProcessingJob[] }) {
  const [tab, setTab] = useState<AnalyticsTab>('overview')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [sort, setSort] = useState<PlayerSort>({ key: 'track_id', descending: false })
  const [assignmentsChanged, setAssignmentsChanged] = useState(false)
  const panel = useRef<HTMLDivElement>(null)
  const switched = useRef(false)
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

  useEffect(() => {
    // A tab chosen far down a long section opens at the start of the new section.
    if (!switched.current) return
    switched.current = false
    const element = panel.current
    if (element && element.getBoundingClientRect().top < STICKY_OFFSET) element.scrollIntoView?.({ block: 'start' })
  }, [tab])
  function openTab(next: AnalyticsTab) { switched.current = next !== tab; setTab(next) }

  return <div className="mt-6 min-w-0">
    <AnalyticsTabs tab={tab} onChange={openTab} />
    <div ref={panel} className="mt-6 min-w-0 scroll-mt-32 space-y-6" role="tabpanel" id={`analytics-panel-${tab}`} aria-labelledby={`analytics-tab-${tab}`}>
      {tab === 'overview' && <AnalyticsOverview match={match} jobs={jobs} queries={{ players, tactics, assignments, trajectories }} assignmentsChanged={assignmentsChanged} onOpen={openTab}
        current={{ players: currentPlayers, tactics: currentTactics, assignments: currentAssignments, trajectories: trajectoryReady ? trajectories.data : undefined }} />}
      {tab === 'players' && <PlayersPanel matchId={match.id} version={playerVersion} query={players} assignments={currentAssignments} sort={sort} onSort={setSort}
        offset={offset} onOffset={setOffset} selected={selected} onSelect={setSelected} onHeatmap={() => openTab('heatmap')} />}
      {tab === 'heatmap' && <HeatmapPanel key={selected ?? 'none'} matchId={match.id} version={playerVersion} selected={selected} assignments={currentAssignments} onSelect={setSelected} />}
      {tab === 'tactics' && <TeamTacticsPanel matchId={match.id} version={tacticalVersion} query={tactics} assignmentsChanged={assignmentsChanged} />}
      {tab === 'assignments' && <AssignmentsPanel matchId={match.id} query={assignments} canManage={canManage} onChanged={() => setAssignmentsChanged(true)} />}
      {(tab === 'overview' || tab === 'tactics' || tab === 'players') && <AnalyticsJobs matchId={match.id} jobs={jobs} canManage={canManage}
        outputs={{ player_analytics: availabilityOf(players), team_tactical_analytics: availabilityOf(tactics) }}
        trajectoriesReady={trajectoryReady} assignmentsReady={!!currentAssignments && (currentAssignments.length > 0 || trajectories.data?.unique_tracks === 0)} />}
      {tab === 'overview' && <ReportsPanel matchId={match.id} version={`${match.updated_at}:${playerVersion}:${tacticalVersion}:${assignmentVersion}`} jobs={jobs}
        canManage={canManage} playersReady={!!currentPlayers} teamsReady={!!currentTactics} />}
    </div>
  </div>
}

function AnalyticsHeader({ match, video, onRefresh }: { match: FootballMatch; video: UseQueryResult<MatchVideo | null>; onRefresh: () => void }) {
  const chip = 'inline-flex max-w-full items-center gap-1.5 rounded-full border border-line-strong px-2.5 py-1'
  const date = match.match_date ? new Date(match.match_date) : null
  return <header className="relative overflow-hidden rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-7">
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgb(60_203_127/0.12),transparent_60%)]" />
    <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300"><ChartColumnBig aria-hidden="true" className="size-4" />Match analytics</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-balance text-slate-50 sm:text-3xl">{match.title}</h1>
        <p className="mt-2 text-sm text-slate-300">{match.team_a.name} <span className="text-slate-500">vs</span> {match.team_b.name}</p>
        <ul className="mt-4 flex flex-wrap gap-2 text-xs font-medium text-slate-300">
          <li className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-emerald-200">{match.match_format}</li>
          {date && !Number.isNaN(date.getTime()) && <li className={chip}><CalendarDays aria-hidden="true" className="size-3.5 shrink-0 text-slate-500" />{date.toLocaleDateString()}</li>}
          <li className={chip}><Shield aria-hidden="true" className="size-3.5 shrink-0 text-slate-500" /><span className="truncate">{match.club.name}</span></li>
          <li className={chip} title={video.data?.original_filename}>{video.data ? <Video aria-hidden="true" className="size-3.5 shrink-0 text-emerald-300" />
            : <VideoOff aria-hidden="true" className="size-3.5 shrink-0 text-slate-500" />}<span className="truncate">{video.error ? 'Video status unavailable'
              : video.data === undefined ? 'Checking video…' : video.data ? video.data.original_filename : 'No source video yet'}</span></li>
          {match.is_archived && <li className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2.5 py-1 text-amber-200">Archived match</li>}
        </ul>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
        <Link className="button-secondary" to={`/matches/${match.id}`}><ArrowLeft aria-hidden="true" className="size-4" />Match details</Link>
        <button type="button" className="button-secondary" onClick={onRefresh}><RefreshCw aria-hidden="true" className="size-4" />Refresh analytics</button>
      </div>
    </div>
  </header>
}

function Dashboard({ match }: { match: FootballMatch }) {
  const client = useQueryClient()
  const video = useMatchVideo(match.id)
  const jobs = useMatchJobs(match.id, 0, true)
  const currentVideo = video.data
  return <>
    <AnalyticsHeader match={match} video={video} onRefresh={() => void client.resetQueries({ queryKey: mediaKey(match.id) })} />
    <QueryState query={video} /><QueryState query={jobs} />
    {video.isSuccess && !video.data && <div className="analytics-state flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <p className="flex items-center gap-3"><VideoOff aria-hidden="true" className="size-5 shrink-0 text-slate-500" />Upload a valid match video and complete processing before viewing analytics.</p>
      <Link className="button-secondary shrink-0" to={`/matches/${match.id}`}>Go to match details</Link>
    </div>}
    {currentVideo && !video.error && jobs.isSuccess && !jobs.error && <AnalyticsContent key={`${match.id}:${currentVideo.id}`} match={match} video={currentVideo} jobs={jobs.data.items.filter((job) => job.video_id === currentVideo.id)} />}
  </>
}

export function AnalyticsPage() {
  const { matchId } = useParams()
  const match = useRecord<FootballMatch>(`matches/${matchId}`)
  return <section className="min-w-0">
    <QueryState query={match} />
    {match.data && !match.error && <Dashboard key={match.data.id} match={match.data} />}
  </section>
}
