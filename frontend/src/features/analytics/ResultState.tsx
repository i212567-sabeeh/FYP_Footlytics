import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { RotateCw } from 'lucide-react'
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
      <button className="button-secondary mt-4" onClick={() => void query.refetch()}><RotateCw aria-hidden="true" className="size-4" />Retry {name.toLowerCase()}</button>
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
  const [badge, dot] = team === 'team_a' ? ['border-sky-400/35 bg-sky-400/10 text-sky-200', 'bg-sky-400']
    : team === 'team_b' ? ['border-amber-400/35 bg-amber-400/10 text-amber-200', 'bg-amber-400']
      : ['border-slate-500/40 bg-slate-500/10 text-slate-300', 'bg-slate-400']
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${badge}`}>
    <span aria-hidden="true" className={`size-1.5 rounded-full ${dot}`} />{TEAM_LABELS[team]}</span>
}

export function Metric({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return <div className="min-w-0 rounded-xl border border-line bg-canvas/40 p-4"><dt className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</dt>
    <dd className="mt-2 break-words text-xl font-semibold tabular-nums tracking-tight text-slate-50">{value}</dd>
    {hint && <p className="mt-2 text-xs leading-5 text-slate-400">{hint}</p>}
  </div>
}
