import type { UseQueryResult } from '@tanstack/react-query'
import { ArrowLeft, Crosshair, Ruler, Video, VideoOff } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { useCalibration } from '../features/calibration/api'
import { CalibrationEditor } from '../features/calibration/CalibrationEditor'
import { useRecord } from '../features/football/api'
import type { FootballMatch } from '../features/football/types'
import { QueryState } from '../features/football/ui'
import { useMatchVideo } from '../features/media/api'
import type { MatchVideo } from '../features/media/types'

const STATUS = {
  checking: ['Checking calibration…', 'border-line-strong text-slate-300'],
  saved: ['Calibration saved for this video', 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'],
  outdated: ['Saved calibration is out of date', 'border-amber-400/30 bg-amber-400/10 text-amber-200'],
  missing: ['Not calibrated yet', 'border-amber-400/30 bg-amber-400/10 text-amber-200'],
} as const

function CalibrationHeader({ match, video, status }: { match: FootballMatch; video: UseQueryResult<MatchVideo | null>; status: keyof typeof STATUS | null }) {
  const chip = 'inline-flex max-w-full items-center gap-1.5 rounded-full border border-line-strong px-2.5 py-1'
  const source = video.data
  return <header className="relative overflow-hidden rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-7">
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgb(60_203_127/0.12),transparent_60%)]" />
    <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300"><Crosshair aria-hidden="true" className="size-4" />Camera to pitch mapping</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-50 sm:text-3xl">Pitch calibration</h1>
        <p className="mt-2 text-sm text-slate-300">{match.title} <span className="text-slate-500">·</span> {match.team_a.name} <span className="text-slate-500">vs</span> {match.team_b.name}</p>
        <ul className="mt-4 flex flex-wrap gap-2 text-xs font-medium text-slate-300">
          <li className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-emerald-200">{match.match_format}</li>
          <li className={`${chip} tabular-nums`}><Ruler aria-hidden="true" className="size-3.5 shrink-0 text-slate-500" />{`${match.pitch_length_metres} × ${match.pitch_width_metres} m pitch`}</li>
          <li className={chip} title={source?.original_filename}>{source ? <Video aria-hidden="true" className="size-3.5 shrink-0 text-emerald-300" /> : <VideoOff aria-hidden="true" className="size-3.5 shrink-0 text-slate-500" />}
            <span className="truncate">{video.error ? 'Video status unavailable' : video.data === undefined ? 'Checking video…' : source ? `${source.original_filename} · ${source.width} × ${source.height}` : 'No source video yet'}</span></li>
          {status && <li className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${STATUS[status][1]}`}><Crosshair aria-hidden="true" className="size-3.5 shrink-0" />{STATUS[status][0]}</li>}
        </ul>
      </div>
      <Link className="button-secondary shrink-0 self-start" to={`/matches/${match.id}`}><ArrowLeft aria-hidden="true" className="size-4" />Match details</Link>
    </div>
    <p className="relative mt-6 border-t border-line pt-5 text-sm leading-6 text-slate-400">Pairs of matching points on the video frame and the pitch let the backend fit a homography that maps image pixels to pitch metres
      (X along the length, Y along the width, origin top-left). Detection, tracking and coordinate mapping require a current calibration.</p>
  </header>
}

function CalibrationContent({ match }: { match: FootballMatch }) {
  const video = useMatchVideo(match.id)
  const calibration = useCalibration(match.id, video.data?.id)
  const current = calibration.data && calibration.data.video_id === video.data?.id
    && calibration.data.pitch_length_metres === match.pitch_length_metres
    && calibration.data.pitch_width_metres === match.pitch_width_metres ? calibration.data : null
  const status = !video.data ? null : calibration.data === undefined ? 'checking' : current ? 'saved' : calibration.data ? 'outdated' : 'missing'
  return <>
    <CalibrationHeader match={match} video={video} status={calibration.error ? null : status} />
    <div className="mt-6">
      <QueryState query={video} />
      {video.data === null && <p className="panel text-slate-400">Upload a match video before calibrating the pitch.</p>}
      {video.data && !video.error && <>
        <QueryState query={calibration} />
        {calibration.isSuccess && <CalibrationEditor key={`${video.data.id}:${match.pitch_length_metres}:${match.pitch_width_metres}`} match={match} video={video.data} initial={current} />}
      </>}
    </div>
  </>
}

export function CalibrationPage() {
  const { matchId } = useParams()
  const match = useRecord<FootballMatch>(`matches/${matchId}`)
  return <section className="min-w-0">
    <QueryState query={match} />
    {match.data && !match.error && <CalibrationContent key={match.data.id} match={match.data} />}
  </section>
}
