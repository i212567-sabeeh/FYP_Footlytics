import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { FootballMatch } from './types'

/** Compact date block: day, month and year of the match date. */
export function MatchDate({ value }: { value: string | null }) {
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) {
    return <span className="grid w-14 shrink-0 place-items-center rounded-lg border border-line bg-canvas/60 py-3 text-xs text-slate-500">
      <span aria-hidden="true">—</span><span className="sr-only">Date not recorded</span>
    </span>
  }
  return <time dateTime={value ?? undefined} className="grid w-14 shrink-0 place-items-center rounded-lg border border-line bg-canvas/60 py-2 text-center">
    <span className="text-lg font-semibold leading-none tabular-nums text-slate-50">{date.toLocaleDateString(undefined, { day: '2-digit' })}</span>
    <span className="mt-1 text-[11px] font-medium uppercase tracking-wider text-slate-400">{date.toLocaleDateString(undefined, { month: 'short' })}</span>
    <span className="text-[10px] tabular-nums text-slate-500">{date.getFullYear()}</span>
  </time>
}

export function ArchivedBadge() {
  return <span className="rounded-full border border-slate-600/60 px-2 py-0.5 text-slate-300">Archived</span>
}

/** A match list row shared by the dashboard and the match list; `children`
 * holds context-specific status or actions. */
export function MatchRow({ match, children }: { match: FootballMatch; children?: ReactNode }) {
  return <li className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center">
    <div className="flex min-w-0 flex-1 items-center gap-4">
      <MatchDate value={match.match_date} />
      <div className="min-w-0">
        <Link to={`/matches/${match.id}`} className="line-clamp-2 break-words font-medium text-slate-50 transition-colors hover:text-emerald-200 sm:line-clamp-1">{match.title}</Link>
        <p className="mt-1 line-clamp-2 break-words text-sm text-slate-300 sm:line-clamp-1">{match.team_a.name} <span className="text-slate-500">vs</span> {match.team_b.name}</p>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
          <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 font-medium text-emerald-200">{match.match_format}</span>
          <span className="min-w-0 truncate">{match.club.name}</span>
          {match.is_archived && <ArchivedBadge />}
        </p>
      </div>
    </div>
    {children && <div className="flex items-center justify-between gap-4 pl-18 sm:justify-end sm:pl-0">{children}</div>}
  </li>
}
