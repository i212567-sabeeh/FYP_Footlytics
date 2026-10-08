import type { ReactNode } from 'react'
import { useMutation, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { CircleDashed, Info, Play, RefreshCw, RotateCw, Route, ScanSearch } from 'lucide-react'
import { StatusBadge } from '../../components/StatusBadge'
import { ApiError, apiRequest } from '../../api/client'
import { availabilityOf } from '../analytics/results'
import { AvailabilityBadge, Note } from '../analytics/ResultState'
import { ErrorMessage, QueryState } from '../football/ui'
import { mediaKey } from '../media/api'
import { isActiveJob, type ProcessingJob } from '../media/types'
import { FramePreview } from './FramePreview'
import type { ReviewKind, ReviewSummary } from './types'

interface Props {
  matchId: number
  videoId: number | undefined
  kind: ReviewKind
  query: UseQueryResult<ReviewSummary>
  latest: ProcessingJob | undefined
  canManage: boolean
  canRun: boolean
  prerequisite: string | null
}

// What the backend draws on each saved JPEG (app/cv/preview.py) and its limits.
const COPY = {
  detections: {
    title: 'Player Detection', step: 'Step 1 · YOLO person detection', icon: ScanSearch, noun: 'detection', path: 'player-detection', run: 'Run detection',
    legend: [
      'Each green box is a saved person detection, labelled with the detector confidence (for example “person 87%”).',
      'Confidence is the model’s score for “person”, not the chance that the box is a player. Referees, coaches and spectators can be detected; distant or overlapped players can be missed.',
      'Low-confidence candidates kept only for tracking are not drawn as detections.',
    ],
  },
  tracking: {
    title: 'Player Tracking', step: 'Step 2 · ByteTrack tracking', icon: Route, noun: 'tracking', path: 'player-tracking', run: 'Run tracking',
    legend: [
      'Each green box is a saved track observation, labelled with its temporary track ID (for example “ID 7”).',
      'Track IDs belong to this match and result only. They are not player identities and can change when players cross, leave the frame or are hidden.',
      'All boxes share one colour; colour never indicates a team.',
    ],
  },
} as const

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return <div className="min-w-0 rounded-lg border border-line bg-canvas/40 px-3 py-2">
    <dt className="text-xs text-slate-400">{label}</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums text-slate-50">{value}</dd>
  </div>
}

export function ReviewPanel({ matchId, videoId, kind, query, latest, canManage, canRun, prerequisite }: Props) {
  const client = useQueryClient()
  const copy = COPY[kind]
  const action = useMutation({
    mutationFn: (retryId?: number) => apiRequest<ProcessingJob>(retryId === undefined
      ? `matches/${matchId}/jobs/${copy.path}` : `jobs/${retryId}/retry`, { method: 'POST' }),
    onSettled: () => client.invalidateQueries({ queryKey: mediaKey(matchId) }),
  })
  const state = availabilityOf(query)
  const unavailable = state === 'missing' || state === 'stale'
  // A summary for another video is never shown as current.
  const replaced = !!query.data && !query.error && query.data.video_id !== videoId
  const summary = query.data && !query.error && !replaced ? query.data : null
  const failed = latest?.status === 'failed' || latest?.status === 'cancelled'
  const actionError = action.error instanceof ApiError && action.error.status === 503
    ? new Error('The processing queue is unavailable. Try again after the queue service is restored.') : action.error
  const Icon = copy.icon

  return <section className="panel min-w-0" aria-labelledby={`${kind}-heading`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300"><Icon aria-hidden="true" className="size-4" />{copy.step}</p>
        <h2 id={`${kind}-heading`} className="mt-1 text-xl font-semibold">{copy.title}</h2>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {summary ? <StatusBadge status={summary.status} /> : videoId !== undefined && <AvailabilityBadge state={replaced ? 'stale' : state} />}
        {canManage && <button className="button-primary" disabled={!canRun || action.isPending} onClick={() => action.mutate(undefined)}>
          <Play aria-hidden="true" className="size-4" />{action.isPending && action.variables === undefined ? 'Submitting…' : copy.run}</button>}
      </div>
    </div>
    {latest && <div className="mt-4 rounded-xl border border-line bg-canvas/40 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-slate-300">{`Latest job #${latest.id}`}</span><StatusBadge status={latest.status} />
        <span className="tabular-nums text-slate-400">{`${latest.progress_percent}% · Retries: ${latest.retry_count}`}</span>
        {latest.current_stage && (isActiveJob(latest) || failed) && <span className="text-slate-400">{`Stage: ${latest.current_stage.replaceAll('_', ' ')}`}</span>}
        {canManage && failed && <button className="button-secondary min-h-8 px-3 py-1 text-xs sm:ml-auto" aria-label={`Retry ${copy.title} job ${latest.id}`}
          disabled={!canRun || action.isPending} onClick={() => action.mutate(latest.id)}><RotateCw aria-hidden="true" className="size-3.5" />Retry</button>}
      </div>
      {isActiveJob(latest) && <progress className="progress-bar mt-3" max={100} value={latest.progress_percent} aria-label={`${copy.title} progress`} />}
      {latest.error_message && <p className="mt-2 break-words text-red-300">{latest.error_message}</p>}
      {latest.warning_message && <p className="mt-2 break-words text-amber-200">{latest.warning_message}</p>}
    </div>}
    {prerequisite && <Note icon={Info}>{prerequisite}</Note>}
    <ErrorMessage error={actionError} />
    {videoId !== undefined && !unavailable && !replaced && <QueryState query={query} />}
    {(videoId === undefined || unavailable || replaced) && <div className="analytics-state flex items-start gap-4">
      <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-full border border-line-strong text-slate-400">
        {state === 'stale' || replaced ? <RefreshCw className="size-5 text-amber-300" /> : <CircleDashed className="size-5" />}</span>
      <div className="min-w-0">
        <p className="font-medium text-slate-100">{state === 'stale' || replaced ? `The saved player ${copy.noun} results are out of date.` : `No player ${copy.noun} results are available yet.`}</p>
        {unavailable && <p className="mt-1 break-words text-sm">{query.error?.message}</p>}
        {replaced && <p className="mt-1 text-sm">These results belong to a replaced video. Run {copy.noun} again for the current video.</p>}
      </div>
    </div>}
    {summary && <>
      {/* The saved frame comes first; result totals follow it. */}
      <FramePreview key={`${summary.video_id}:${summary.job_id}:${summary.job_updated_at}`} matchId={matchId} kind={kind} summary={summary} />
      <dl className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Stat label="Processed frames" value={summary.processed_frames} />
        {'total_detections' in summary ? <>
          <Stat label="Detections" value={summary.total_detections} />
          <Stat label="Average detections per frame" value={summary.average_detections_per_processed_frame.toFixed(2)} />
          <Stat label="Frame size" value={`${summary.frame_width} × ${summary.frame_height}`} />
        </> : <>
          <Stat label="Unique tracks" value={summary.unique_tracks} />
          <Stat label="Tracked observations" value={summary.tracked_rows} />
          <Stat label="Average visible tracks per frame" value={summary.average_visible_tracks_per_frame.toFixed(2)} />
        </>}
      </dl>
      <div className="mt-4 rounded-xl border border-line bg-canvas/40 p-4 text-xs leading-5 text-slate-400">
        <p className="flex items-center gap-2 font-semibold text-slate-300"><Info aria-hidden="true" className="size-4 text-slate-500" />{`Reading this preview · result from job #${summary.job_id}`}</p>
        <ul className="mt-2 list-disc space-y-1 pl-5">{copy.legend.map((line) => <li key={line}>{line}</li>)}</ul>
      </div>
    </>}
  </section>
}
