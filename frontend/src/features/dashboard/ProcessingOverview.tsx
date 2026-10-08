import type { UseQueryResult } from '@tanstack/react-query'
import { Activity, CircleCheck, CircleDashed, CircleSlash, CircleX, LoaderCircle, TriangleAlert, type LucideIcon } from 'lucide-react'
import type { FootballMatch, Page } from '../football/types'
import type { JobResult } from './RecentMatches'
import { countStates, PROCESSING_ORDER, type ProcessingState } from './summary'

const STATES: Record<ProcessingState, [string, LucideIcon, string]> = {
  active: ['Queued or running', LoaderCircle, 'text-sky-300'],
  failed: ['Failed', CircleX, 'text-red-300'],
  completed_with_warnings: ['Completed with warnings', TriangleAlert, 'text-amber-300'],
  completed: ['Completed', CircleCheck, 'text-emerald-300'],
  cancelled: ['Cancelled', CircleSlash, 'text-slate-400'],
  none: ['No processing yet', CircleDashed, 'text-slate-400'],
}

/** Counts of each listed match's latest job state, scoped to Latest matches;
 * derived from the same per-match results, so it adds no requests. */
export function ProcessingOverview({ matches, jobs }: {
  matches: Pick<UseQueryResult<Page<FootballMatch>>, 'data' | 'error'>; jobs: readonly JobResult[]
}) {
  const listed = matches.data?.items.length ?? 0
  const latest = jobs.flatMap((result) => result.data ? [result.data.items[0]] : [])
  const failed = jobs.filter((result) => result.error).length
  const counts = countStates(latest)
  return <section aria-labelledby="processing-heading" className="panel min-w-0 p-5">
    <div className="flex items-center gap-2">
      <Activity aria-hidden="true" className="size-4 text-emerald-300" />
      <h2 id="processing-heading" className="text-base font-semibold text-slate-50">Processing</h2>
    </div>
    <p className="mt-1 text-xs text-slate-400">Latest job for each match in Latest matches</p>
    {matches.error ? <p className="mt-4 text-sm text-slate-400">Processing status appears once matches load.</p>
      : !matches.data ? <p className="mt-4 text-sm text-slate-400">Loading matches…</p>
        : !listed ? <p className="mt-4 text-sm text-slate-400">No matches to summarise yet.</p>
          : <>
            <ul className="mt-4 space-y-2">
              {PROCESSING_ORDER.filter((state) => counts[state]).map((state) => {
                const [label, Icon, tone] = STATES[state]
                return <li key={state} className="flex items-center justify-between gap-3 rounded-lg border border-line bg-canvas/40 px-3 py-2.5">
                  <span className="flex items-center gap-2.5 text-sm text-slate-200">
                    <Icon aria-hidden="true" className={`size-4 shrink-0 ${tone}`} />{label}
                  </span>
                  <span className="text-sm font-semibold tabular-nums text-slate-50">{counts[state]}</span>
                </li>
              })}
            </ul>
            {latest.length + failed < listed && <p className="mt-3 text-xs text-slate-400">Loading job status…</p>}
            {failed > 0 && <p className="mt-3 text-xs text-amber-200">Job status could not be loaded for {failed} of {listed} matches.</p>}
          </>}
  </section>
}
