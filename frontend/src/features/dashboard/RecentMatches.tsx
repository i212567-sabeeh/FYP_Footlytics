import type { UseQueryResult } from '@tanstack/react-query'
import { Link } from 'react-router'
import { StatusBadge } from '../../components/StatusBadge'
import { MatchRow } from '../football/MatchRow'
import type { FootballMatch, Page } from '../football/types'
import { QueryState } from '../football/ui'
import { isActiveJob, JOB_LABELS, type ProcessingJob } from '../media/types'

export type JobResult = Pick<UseQueryResult<Page<ProcessingJob>>, 'data' | 'error'>
type MatchesQuery = Pick<UseQueryResult<Page<FootballMatch>>, 'data' | 'error' | 'isPending' | 'refetch'>

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
        {query.data.items.map((match, index) => <MatchRow key={match.id} match={match}>
          {(jobs || showAnalytics) && <>
            {jobs && <LatestJob result={jobs[index]} />}
            {showAnalytics && <Link to={`/matches/${match.id}/analytics`} aria-label={`Analytics for ${match.title}`} className="button-secondary shrink-0">
              Analytics
            </Link>}
          </>}
        </MatchRow>)}
      </ul> : <p className="py-6 text-sm text-slate-400">No matches are available yet.</p>)}
    </div>
  </section>
}
