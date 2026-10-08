import type { UseQueryResult } from '@tanstack/react-query'
import { Link } from 'react-router'
import { StatusBadge } from '../../components/StatusBadge'
import type { FootballMatch, Page } from '../football/types'
import { QueryState } from '../football/ui'
import { isActiveJob, JOB_LABELS, type ProcessingJob } from '../media/types'

export type JobResult = Pick<UseQueryResult<Page<ProcessingJob>>, 'data' | 'error'>
type MatchesQuery = Pick<UseQueryResult<Page<FootballMatch>>, 'data' | 'error' | 'isPending' | 'refetch'>

function MatchDate({ value }: { value: string | null }) {
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

function LatestJob({ result }: { result: JobResult | undefined }) {
  if (result?.error) return <span className="text-xs text-slate-400">Status could not be loaded</span>
  if (!result?.data) return <span className="h-6 w-24 animate-pulse rounded-full bg-slate-800 motion-reduce:animate-none"><span className="sr-only">Loading job status</span></span>
  const job = result.data.items[0]
  if (!job) return <span className="text-xs text-slate-400">No processing yet</span>
  return <span className="flex flex-col items-start gap-1 sm:items-end">
    <StatusBadge status={job.status} />
    <span className="text-xs text-slate-400">{JOB_LABELS[job.job_type]}{isActiveJob(job) ? ` · ${job.progress_percent}%` : ''}</span>
  </span>
}

/** The match API orders by match date, newest first, so this page of results is
 * genuinely the latest. Job status appears only for roles that may read jobs. */
export function RecentMatches({ query, jobs, showAnalytics, className = '' }: {
  query: MatchesQuery; jobs: readonly JobResult[] | undefined; showAnalytics: boolean; className?: string
}) {
  return <section aria-labelledby="latest-matches-heading" className={`panel min-w-0 p-0 ${className}`}>
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
      <div>
        <h2 id="latest-matches-heading" className="text-base font-semibold text-slate-50">Latest matches</h2>
        <p className="text-xs text-slate-400">Newest match date first</p>
      </div>
      <Link to="/matches" className="record-link text-sm">View all matches</Link>
    </div>
    <div className="px-5">
      <QueryState query={query} />
      {query.data && (query.data.items.length ? <ul className="divide-y divide-line">
        {query.data.items.map((match, index) => <li key={match.id} className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center">
          <div className="flex min-w-0 flex-1 items-center gap-4">
            <MatchDate value={match.match_date} />
            <div className="min-w-0">
              <Link to={`/matches/${match.id}`} className="block truncate font-medium text-slate-50 transition-colors hover:text-emerald-200">{match.title}</Link>
              <p className="mt-1 truncate text-sm text-slate-300">{match.team_a.name} <span className="text-slate-500">vs</span> {match.team_b.name}</p>
              <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
                <span>{match.match_format} · {match.club.name}</span>
                {match.is_archived && <span className="rounded-full border border-slate-600/60 px-2 py-0.5 text-slate-300">Archived</span>}
              </p>
            </div>
          </div>
          {(jobs || showAnalytics) && <div className="flex items-center justify-between gap-4 sm:justify-end">
            {jobs && <LatestJob result={jobs[index]} />}
            {showAnalytics && <Link to={`/matches/${match.id}/analytics`} aria-label={`Analytics for ${match.title}`} className="button-secondary shrink-0">
              Analytics
            </Link>}
          </div>}
        </li>)}
      </ul> : <p className="py-6 text-sm text-slate-400">No matches are available yet.</p>)}
    </div>
  </section>
}
