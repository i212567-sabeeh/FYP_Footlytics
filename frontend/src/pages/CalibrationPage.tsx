import { Link, useParams } from 'react-router'
import { useCalibration } from '../features/calibration/api'
import { CalibrationEditor } from '../features/calibration/CalibrationEditor'
import { useRecord } from '../features/football/api'
import type { FootballMatch } from '../features/football/types'
import { Heading, QueryState } from '../features/football/ui'
import { useMatchVideo } from '../features/media/api'

function CalibrationContent({ match }: { match: FootballMatch }) {
  const video = useMatchVideo(match.id)
  const calibration = useCalibration(match.id, video.data?.id)
  const current = calibration.data && calibration.data.video_id === video.data?.id
    && calibration.data.pitch_length_metres === match.pitch_length_metres
    && calibration.data.pitch_width_metres === match.pitch_width_metres ? calibration.data : null
  return <>
    <QueryState query={video} />
    {video.data === null && <p className="panel text-slate-400">Upload a match video before calibrating the pitch.</p>}
    {video.data && !video.error && <>
      <QueryState query={calibration} />
      {calibration.isSuccess && <CalibrationEditor key={`${video.data.id}:${match.pitch_length_metres}:${match.pitch_width_metres}`} match={match} video={video.data} initial={current} />}
    </>}
  </>
}

export function CalibrationPage() {
  const { matchId } = useParams()
  const match = useRecord<FootballMatch>(`matches/${matchId}`)
  return <section>
    <Link className="record-link" to={`/matches/${matchId}`}>Back to Match Details</Link>
    <div className="mt-6"><Heading title="Pitch calibration" /></div>
    <QueryState query={match} />
    {match.data && !match.error && <>
      <p className="mb-6 text-slate-300">{match.data.title} · {match.data.match_format}</p>
      <CalibrationContent key={match.data.id} match={match.data} />
    </>}
  </section>
}
