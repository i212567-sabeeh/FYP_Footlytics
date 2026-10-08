import { useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { ArrowLeft, Crosshair, Lock, RefreshCw, Route, ScanSearch, Video, VideoOff } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { Note } from '../features/analytics/ResultState'
import { useCalibration } from '../features/calibration/api'
import { useRecord } from '../features/football/api'
import { useCapabilities } from '../features/football/hooks'
import type { FootballMatch } from '../features/football/types'
import { QueryState } from '../features/football/ui'
import { mediaKey, useMatchJobs, useMatchVideo } from '../features/media/api'
import { isActiveJob, type MatchVideo } from '../features/media/types'
import { useReviewSummary } from '../features/review/api'
import { ReviewPanel } from '../features/review/ReviewPanel'

type CalibrationState = 'checking' | 'current' | 'outdated' | 'missing' | 'error'
const CALIBRATION: Record<CalibrationState, [string, string]> = {
  checking: ['Checking calibration…', 'border-line-strong text-slate-300'],
  current: ['Calibration current', 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'],
  outdated: ['Calibration out of date', 'border-amber-400/30 bg-amber-400/10 text-amber-200'],
  missing: ['No pitch calibration', 'border-amber-400/30 bg-amber-400/10 text-amber-200'],
  error: ['Calibration status unavailable', 'border-line-strong text-slate-300'],
}
const seconds = (value: number) => value < 60 ? `${value.toFixed(1)} s` : `${Math.floor(value / 60)}:${String(Math.round(value % 60)).padStart(2, '0')}`

function ReviewHeader({ match, video, calibration, onRefresh }: {
  match: FootballMatch; video: UseQueryResult<MatchVideo | null>; calibration: CalibrationState | null; onRefresh: () => void
}) {
  const chip = 'inline-flex max-w-full items-center gap-1.5 rounded-full border border-line-strong px-2.5 py-1'
  const source = video.data
  return <header className="relative overflow-hidden rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-7">
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgb(60_203_127/0.12),transparent_60%)]" />
    <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300"><ScanSearch aria-hidden="true" className="size-4" />Detection &amp; tracking review</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-balance text-slate-50 sm:text-3xl">{match.title}</h1>
        <p className="mt-2 text-sm text-slate-300">{match.team_a.name} <span className="text-slate-500">vs</span> {match.team_b.name}</p>
        <ul className="mt-4 flex flex-wrap gap-2 text-xs font-medium text-slate-300">
          <li className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-emerald-200">{match.match_format}</li>
          <li className={chip} title={source?.original_filename}>{source ? <Video aria-hidden="true" className="size-3.5 shrink-0 text-emerald-300" /> : <VideoOff aria-hidden="true" className="size-3.5 shrink-0 text-slate-500" />}
            <span className="truncate">{video.error ? 'Video status unavailable' : video.data === undefined ? 'Checking video…' : source ? source.original_filename : 'No source video yet'}</span></li>
          {source && <li className={`${chip} tabular-nums`}>{`${source.width} × ${source.height} · ${Number.isInteger(source.fps) ? source.fps : source.fps.toFixed(2)} fps · ${seconds(source.duration_seconds)}`}</li>}
          {calibration && <li className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${CALIBRATION[calibration][1]}`}>
            <Crosshair aria-hidden="true" className="size-3.5 shrink-0" />{CALIBRATION[calibration][0]}</li>}
        </ul>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
        <Link className="button-secondary" to={`/matches/${match.id}`}><ArrowLeft aria-hidden="true" className="size-4" />Match details</Link>
        {source && <Link className="button-secondary" to={`/matches/${match.id}/calibration`}><Crosshair aria-hidden="true" className="size-4" />Pitch calibration</Link>}
        <button type="button" className="button-secondary" onClick={onRefresh}><RefreshCw aria-hidden="true" className="size-4" />Refresh review</button>
      </div>
    </div>
    <div className="relative mt-6 grid gap-3 border-t border-line pt-5 text-sm leading-6 text-slate-400 md:grid-cols-2">
      <p className="flex gap-3"><ScanSearch aria-hidden="true" className="mt-1 size-4 shrink-0 text-emerald-300" />
        <span><span className="font-medium text-slate-200">Detection (YOLO)</span> finds people in each processed frame and scores every box.</span></p>
      <p className="flex gap-3"><Route aria-hidden="true" className="mt-1 size-4 shrink-0 text-emerald-300" />
        <span><span className="font-medium text-slate-200">Tracking (ByteTrack)</span> links those detections across processed frames into temporary track IDs.</span></p>
    </div>
  </header>
}

function ReviewContent({ match }: { match: FootballMatch }) {
  const client = useQueryClient()
  const capability = useCapabilities()
  const video = useMatchVideo(match.id)
  const calibration = useCalibration(match.id, video.data?.id)
  const jobs = useMatchJobs(match.id, 0, true)
  const active = jobs.data?.items.some(isActiveJob) ?? false
  // Completion/retry changes refresh current summaries; progress updates alone
  // do not reload a saved image every two seconds.
  const version = jobs.data?.items.map((job) => `${job.id}:${job.status}:${job.retry_count}`).join('|') ?? ''
  const detection = useReviewSummary(match.id, 'detections', video.data?.id, version, jobs.isSuccess && !video.error)
  const tracking = useReviewSummary(match.id, 'tracking', video.data?.id, version, jobs.isSuccess && !video.error)
  const canManage = capability.match && match.club.is_active && !match.is_archived
  const calibrated = !!calibration.data && calibration.data.video_id === video.data?.id
    && calibration.data.pitch_length_metres === match.pitch_length_metres
    && calibration.data.pitch_width_metres === match.pitch_width_metres && !calibration.error
  const calibrationState: CalibrationState | null = !video.data ? null : calibration.error ? 'error'
    : calibration.data === undefined ? 'checking' : !calibration.data ? 'missing' : calibrated ? 'current' : 'outdated'
  const ready = calibrated && jobs.isSuccess && !jobs.error && !!video.data && !video.error && !active
  const prerequisite = !video.data ? 'Upload a match video first.' : !calibrated ? 'Save a current pitch calibration before starting processing.' : active ? 'A processing job is queued or running.' : null

  return <>
    <ReviewHeader match={match} video={video} calibration={calibrationState} onRefresh={() => void client.invalidateQueries({ queryKey: mediaKey(match.id) })} />
    <QueryState query={video} />
    <QueryState query={jobs} />
    {video.data && <QueryState query={calibration} />}
    {!canManage && <Note icon={Lock}>Read-only review.</Note>}
    {!video.error && !jobs.error && jobs.isSuccess && <div className="mt-6 grid min-w-0 gap-6 2xl:grid-cols-2">
      <ReviewPanel matchId={match.id} videoId={video.data?.id} kind="detections" query={detection}
        latest={jobs.data?.items.find((job) => job.video_id === video.data?.id && job.job_type === 'player_detection')}
        canManage={canManage} canRun={ready} prerequisite={prerequisite} />
      <ReviewPanel matchId={match.id} videoId={video.data?.id} kind="tracking" query={tracking}
        latest={jobs.data?.items.find((job) => job.video_id === video.data?.id && job.job_type === 'player_tracking')}
        canManage={canManage} canRun={ready && detection.isSuccess && !detection.error}
        prerequisite={prerequisite ?? (!detection.isSuccess || detection.error ? 'Current detection results are required before tracking.' : null)} />
    </div>}
  </>
}

export function ReviewPage() {
  const { matchId } = useParams()
  const match = useRecord<FootballMatch>(`matches/${matchId}`)
  return <section className="min-w-0">
    <QueryState query={match} />
    {match.data && !match.error && <ReviewContent key={match.data.id} match={match.data} />}
  </section>
}
