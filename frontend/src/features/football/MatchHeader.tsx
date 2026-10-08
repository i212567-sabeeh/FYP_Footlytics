import type { ReactNode } from 'react'
import { Archive, ArchiveRestore, CalendarDays, ChartColumnBig, Crosshair, MapPin, Pencil, Ruler, ScanSearch, Shield, UserRound, Video, VideoOff, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router'
import { useMatchVideo } from '../media/api'
import { useCapabilities } from './hooks'
import type { FootballMatch } from './types'
import { DateText } from './ui'

function Team({ name, side }: { name: string; side: 'A' | 'B' }) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part.charAt(0).toUpperCase()).join('')
  return <div className="flex min-w-0 items-center gap-3">
    <span aria-hidden="true" className={`grid size-11 shrink-0 place-items-center rounded-full bg-canvas text-sm font-semibold ring-2 ${side === 'A'
      ? 'text-sky-200 ring-sky-400/50' : 'text-amber-200 ring-amber-400/50'}`}>{initials || side}</span>
    <div className="min-w-0">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">Team {side}</p>
      <p className="truncate text-lg font-semibold text-slate-50">{name}</p>
    </div>
  </div>
}

function Detail({ icon: Icon, label, children }: { icon: LucideIcon; label: string; children: ReactNode }) {
  return <div className="flex min-w-0 gap-3">
    <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
    <div className="min-w-0"><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-0.5 break-words text-sm text-slate-200">{children}</dd></div>
  </div>
}

/** Summary of the match and its existing navigation and editing controls. */
export function MatchHeader({ match, onEdit, onArchive, archiving }: {
  match: FootballMatch; onEdit: () => void; onArchive: () => void; archiving: boolean
}) {
  const capability = useCapabilities()
  const video = useMatchVideo(match.id)
  const hasVideo = Boolean(video.data) && !video.error
  const action = 'button-secondary'
  return <header className="relative overflow-hidden rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-8">
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgb(60_203_127/0.12),transparent_60%)]" />
    <div className="relative flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
          <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-emerald-200">{match.match_format}</span>
          {match.is_archived && <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2.5 py-1 text-amber-200">Archived match</span>}
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-2.5 py-1 text-slate-300">
            {hasVideo ? <Video aria-hidden="true" className="size-3.5 text-emerald-300" /> : <VideoOff aria-hidden="true" className="size-3.5 text-slate-500" />}
            {video.error ? 'Video status unavailable' : video.data === undefined ? 'Checking video…' : video.data ? 'Source video ready' : 'No source video yet'}
          </span>
        </div>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight text-balance text-slate-50 sm:text-3xl">{match.title}</h1>
        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-3">
          <Team name={match.team_a.name} side="A" />
          <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">vs</span>
          <Team name={match.team_b.name} side="B" />
        </div>
      </div>
      <div className="flex flex-wrap gap-2 xl:max-w-md xl:justify-end">
        {/* The review and analytics routes admit the same staff roles. */}
        {capability.analytics && <Link className="button-primary" to={`/matches/${match.id}/analytics`}><ChartColumnBig aria-hidden="true" className="size-4" />View Analytics</Link>}
        {capability.analytics && <Link className={action} to={`/matches/${match.id}/review`}><ScanSearch aria-hidden="true" className="size-4" />Player Detection &amp; Tracking Review</Link>}
        {hasVideo && <Link className={action} to={`/matches/${match.id}/calibration`}><Crosshair aria-hidden="true" className="size-4" />Calibrate Pitch</Link>}
        {capability.match && match.club.is_active && <>
          <button type="button" className={action} onClick={onEdit}><Pencil aria-hidden="true" className="size-4" />Edit match</button>
          <button type="button" className={action} disabled={archiving} onClick={onArchive}>
            {match.is_archived ? <ArchiveRestore aria-hidden="true" className="size-4" /> : <Archive aria-hidden="true" className="size-4" />}
            {match.is_archived ? 'Restore match' : 'Archive match'}</button>
        </>}
      </div>
    </div>
    <dl className="relative mt-6 grid gap-5 border-t border-line pt-6 sm:grid-cols-2 xl:grid-cols-4">
      <Detail icon={Shield} label="Club"><Link className="record-link" to={`/clubs/${match.club_id}`}>{match.club.name}</Link></Detail>
      <Detail icon={CalendarDays} label="Match date (local)"><DateText value={match.match_date} /></Detail>
      <Detail icon={Ruler} label="Pitch dimensions">{match.pitch_length_metres} m length (X) × {match.pitch_width_metres} m width (Y)</Detail>
      <Detail icon={MapPin} label="Venue">{match.venue || 'Not recorded'}</Detail>
      <Detail icon={UserRound} label="Created by">{match.created_by.full_name}</Detail>
    </dl>
    {match.notes && <p className="relative mt-5 whitespace-pre-wrap rounded-lg border border-line bg-canvas/40 p-4 text-sm leading-6 text-slate-300">{match.notes}</p>}
  </header>
}
