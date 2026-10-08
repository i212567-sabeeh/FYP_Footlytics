import { useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { useCalibration } from '../features/calibration/api'
import { useRecord } from '../features/football/api'
import { useCapabilities } from '../features/football/hooks'
import type { FootballMatch } from '../features/football/types'
import { Heading, QueryState } from '../features/football/ui'
import { mediaKey, useMatchJobs, useMatchVideo } from '../features/media/api'
import { isActiveJob } from '../features/media/types'
import { useReviewSummary } from '../features/review/api'
import { ReviewPanel } from '../features/review/ReviewPanel'

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
  const ready = calibrated && jobs.isSuccess && !jobs.error && !!video.data && !video.error && !active
  const prerequisite = !video.data ? 'Upload a match video first.' : !calibrated ? 'Save a current pitch calibration before starting processing.' : active ? 'A processing job is queued or running.' : null

  return <>
    <div className="flex flex-wrap items-center gap-4">
      <button className="button-secondary" onClick={() => void client.invalidateQueries({ queryKey: mediaKey(match.id) })}>Refresh review</button>
      {video.data && <Link className="record-link" to={`/matches/${match.id}/calibration`}>Pitch calibration</Link>}
    </div>
    <QueryState query={video} />
    <QueryState query={jobs} />
    {video.data && <QueryState query={calibration} />}
    {!canManage && <p className="mt-4 text-sm text-slate-400">Read-only review.</p>}
    {!video.error && !jobs.error && jobs.isSuccess && <>
      <ReviewPanel matchId={match.id} videoId={video.data?.id} kind="detections" query={detection}
        latest={jobs.data?.items.find((job) => job.video_id === video.data?.id && job.job_type === 'player_detection')}
        canManage={canManage} canRun={ready} prerequisite={prerequisite} />
      <ReviewPanel matchId={match.id} videoId={video.data?.id} kind="tracking" query={tracking}
        latest={jobs.data?.items.find((job) => job.video_id === video.data?.id && job.job_type === 'player_tracking')}
        canManage={canManage} canRun={ready && detection.isSuccess && !detection.error}
        prerequisite={prerequisite ?? (!detection.isSuccess || detection.error ? 'Current detection results are required before tracking.' : null)} />
    </>}
  </>
}

export function ReviewPage() {
  const { matchId } = useParams()
  const match = useRecord<FootballMatch>(`matches/${matchId}`)
  return <section>
    <Link className="record-link" to={`/matches/${matchId}`}>Back to Match Details</Link>
    <div className="mt-6"><Heading title="Player Detection & Tracking Review" /></div>
    <QueryState query={match} />
    {match.data && !match.error && <>
      <p className="mb-6 text-slate-300">{match.data.title}</p>
      <ReviewContent key={match.data.id} match={match.data} />
    </>}
  </section>
}
