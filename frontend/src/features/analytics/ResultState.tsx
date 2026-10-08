import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { StatusBadge } from '../../components/StatusBadge'
import { ApiError } from '../../api/client'
import { TEAM_LABELS, type TeamAssignment } from './types'

type State = Pick<UseQueryResult, 'isPending' | 'isFetching' | 'error' | 'refetch'>
export function ResultState({ query, name, children, assignmentsChanged = false }: {
  query: State; name: string; children?: ReactNode; assignmentsChanged?: boolean
}) {
  if (query.error) {
    const error = query.error
    const unavailable = error instanceof ApiError && [404, 409].includes(error.status)
    const stale = unavailable && /stale|changed|replaced/i.test(error.message)
    return <div className="analytics-state" role={unavailable ? 'status' : 'alert'}>
      <div className="mb-3"><StatusBadge status={stale ? 'stale' : unavailable ? 'unavailable' : 'failed'} /></div>
      <p className="font-medium text-slate-100">{assignmentsChanged && unavailable
        ? 'Team assignments changed. Regenerate team tactical analytics.'
        : stale ? `${name} need to be regenerated.`
        : unavailable ? `${name} have not been generated yet.`
        : error instanceof ApiError && error.status === 403 ? 'Access denied for these analytics.'
        : `${name} could not be loaded.`}</p>
      <p className="mt-2 break-words text-sm text-slate-400">{error.message}</p>
      <button className="button-secondary mt-4" onClick={() => void query.refetch()}>Retry {name.toLowerCase()}</button>
    </div>
  }
  if (query.isPending || query.isFetching) return <div className="analytics-state min-h-32" role="status" aria-live="polite">
    <p className="text-sm text-slate-400">{query.isPending ? 'Loading' : 'Refreshing'} {name.toLowerCase()}…</p>
    <div className="mt-5 h-3 w-2/3 animate-pulse rounded bg-slate-800 motion-reduce:animate-none" />
    <div className="mt-3 h-3 w-1/3 animate-pulse rounded bg-slate-800 motion-reduce:animate-none" />
  </div>
  return children
}

export function TeamBadge({ trackId, assignments }: { trackId: number; assignments: TeamAssignment[] | undefined }) {
  if (!assignments) return <span className="text-sm text-slate-400">Team unavailable</span>
  const team = assignments.find((row) => row.track_id === trackId)?.effective_team ?? 'unknown'
  return <span className={`inline-block rounded-full border px-2.5 py-1 text-xs font-medium ${team === 'team_a'
    ? 'border-sky-900 bg-sky-950 text-sky-200' : team === 'team_b'
      ? 'border-amber-900 bg-amber-950 text-amber-200' : 'border-slate-700 text-slate-300'}`}>{TEAM_LABELS[team]}</span>
}

export function Metric({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return <div className="min-w-0 rounded-lg border border-slate-800 bg-slate-950/30 p-4"><dt className="text-sm text-slate-400">{label}</dt>
    <dd className="mt-2 break-words text-xl font-semibold tabular-nums tracking-tight text-slate-100">{value}</dd>
    {hint && <p className="mt-2 text-xs leading-5 text-slate-400">{hint}</p>}
  </div>
}
