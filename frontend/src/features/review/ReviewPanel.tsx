import { StatusBadge } from '../../components/StatusBadge'
import { useMutation, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { ApiError, apiRequest } from '../../api/client'
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

export function ReviewPanel({ matchId, videoId, kind, query, latest, canManage, canRun, prerequisite }: Props) {
  const client = useQueryClient()
  const detection = kind === 'detections'
  const title = detection ? 'Player Detection' : 'Player Tracking'
  const action = useMutation({
    mutationFn: () => apiRequest<ProcessingJob>(`matches/${matchId}/jobs/${detection ? 'player-detection' : 'player-tracking'}`, { method: 'POST' }),
    onSettled: () => client.invalidateQueries({ queryKey: mediaKey(matchId) }),
  })
  const unavailable = query.error instanceof ApiError && [404, 409].includes(query.error.status)
  const summary = query.data && !query.error && query.data.video_id === videoId ? query.data : null

  return <section className="panel mt-6" aria-labelledby={`${kind}-heading`}>
    <div className="flex flex-wrap items-center justify-between gap-4">
      <h2 id={`${kind}-heading`} className="text-xl font-semibold">{title}</h2>
      {canManage && <button className="button-primary" disabled={!canRun || action.isPending} onClick={() => action.mutate()}>{action.isPending ? 'Submitting…' : detection ? 'Run detection' : 'Run tracking'}</button>}
    </div>
    <p className="mt-3 text-sm leading-6 text-slate-400">{detection
      ? 'Inspect saved YOLO person boxes and confidence before continuing to tracking. Person detections can include referees or other people.'
      : 'Step through saved ByteTrack observations to check whether IDs persist. IDs belong to this match and result, and are not player identities.'}</p>
    {prerequisite && <p className="mt-3 text-sm text-slate-400">{prerequisite}</p>}
    {latest && <div className="mt-4 rounded-lg border border-slate-800 p-3 text-sm">
      <p>Latest job #{latest.id}: <StatusBadge status={latest.status} /> · {latest.progress_percent}%</p>
      {latest.current_stage && <p className="mt-2 text-slate-400">Stage: {latest.current_stage.replaceAll('_', ' ')}</p>}
      {isActiveJob(latest) && <progress className="mt-3 h-2 w-full accent-emerald-400" max={100} value={latest.progress_percent} aria-label={`${title} progress`} />}
      {latest.error_message && <p className="mt-2 text-red-300">{latest.error_message}</p>}
      {latest.warning_message && <p className="mt-2 text-amber-200">{latest.warning_message}</p>}
    </div>}
    <ErrorMessage error={action.error} />
    {videoId !== undefined && !unavailable && <QueryState query={query} />}
    {(videoId === undefined || unavailable) && <div className="mt-5 text-slate-400">
      <p>No player {detection ? 'detection' : 'tracking'} results are available yet.</p>
      {unavailable && <p className="mt-2 text-sm">{query.error?.message}</p>}
    </div>}
    {summary && <>
      <p className="mt-5 text-sm text-slate-400">Showing current result from job #{summary.job_id} · <StatusBadge status={summary.status} /></p>
      <dl className="mt-4 grid gap-4 sm:grid-cols-3">
        <div><dt className="text-sm text-slate-400">Processed frames</dt><dd className="mt-1 text-xl">{summary.processed_frames}</dd></div>
        {'total_detections' in summary ? <>
          <div><dt className="text-sm text-slate-400">Detections</dt><dd className="mt-1 text-xl">{summary.total_detections}</dd></div>
          <div><dt className="text-sm text-slate-400">Average detections per frame</dt><dd className="mt-1 text-xl">{summary.average_detections_per_processed_frame.toFixed(2)}</dd></div>
        </> : <>
          <div><dt className="text-sm text-slate-400">Unique tracks</dt><dd className="mt-1 text-xl">{summary.unique_tracks}</dd></div>
          <div><dt className="text-sm text-slate-400">Tracked observations</dt><dd className="mt-1 text-xl">{summary.tracked_rows}</dd></div>
          <div><dt className="text-sm text-slate-400">Average visible tracks per frame</dt><dd className="mt-1 text-xl">{summary.average_visible_tracks_per_frame.toFixed(2)}</dd></div>
        </>}
      </dl>
      <FramePreview key={`${summary.video_id}:${summary.job_id}:${summary.job_updated_at}`} matchId={matchId} kind={kind} summary={summary} />
    </>}
  </section>
}
