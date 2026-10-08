import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { CircleCheck, CircleDashed, CircleX, LoaderCircle, Lock, RefreshCw, RotateCw, type LucideIcon } from 'lucide-react'
import { availabilityOf, resultMessage, TEAM_TONES, type Availability } from './results'
import { TEAM_LABELS, type TeamAssignment } from './types'

type State = Pick<UseQueryResult, 'isPending' | 'isFetching' | 'error' | 'refetch'>

const AVAILABILITY: Record<Availability, [label: string, icon: LucideIcon, tone: string]> = {
  checking: ['Checking…', LoaderCircle, 'border-slate-500/40 bg-slate-500/10 text-slate-300'],
  available: ['Available', CircleCheck, 'border-emerald-400/35 bg-emerald-400/10 text-emerald-200'],
  stale: ['Needs regeneration', RefreshCw, 'border-amber-400/35 bg-amber-400/10 text-amber-200'],
  missing: ['Not generated', CircleDashed, 'border-slate-500/40 bg-slate-500/10 text-slate-300'],
  denied: ['Access denied', Lock, 'border-red-400/35 bg-red-400/10 text-red-200'],
  error: ['Could not load', CircleX, 'border-red-400/35 bg-red-400/10 text-red-200'],
}

/** An inline explanation: amber for blocking prerequisites, slate for read-only notes. */
export function Note({ icon: Icon, tone = 'slate', children }: { icon: LucideIcon; tone?: 'amber' | 'slate'; children: ReactNode }) {
  return <p className={`mt-3 flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm leading-6 ${tone === 'amber'
    ? 'border-amber-400/25 bg-amber-400/5 text-amber-200' : 'border-line bg-canvas/40 text-slate-300'}`}>
    <Icon aria-hidden="true" className="mt-1 size-4 shrink-0" />{children}</p>
}

export function AvailabilityBadge({ state }: { state: Availability }) {
  const [label, Icon, tone] = AVAILABILITY[state]
  return <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${tone}`}>
    <Icon aria-hidden="true" className={`size-3.5 shrink-0${state === 'checking' ? ' animate-spin motion-reduce:animate-none' : ''}`} />{label}</span>
}

export function ResultState({ query, name, children, assignmentsChanged = false }: {
  query: State; name: string; children?: ReactNode; assignmentsChanged?: boolean
}) {
  if (query.error) {
    const state = availabilityOf(query)
    const [, Icon, tone] = AVAILABILITY[state]
    // Missing or stale results are expected states; other failures are alerts.
    return <div className="analytics-state flex flex-col gap-4 sm:flex-row sm:items-start" role={state === 'missing' || state === 'stale' ? 'status' : 'alert'}>
      <span aria-hidden="true" className={`grid size-10 shrink-0 place-items-center rounded-full border ${tone}`}><Icon className="size-5" /></span>
      <div className="min-w-0">
        <p className="font-medium text-slate-100">{resultMessage(state, name, assignmentsChanged)}</p>
        <p className="mt-1 break-words text-sm text-slate-400">{query.error.message}</p>
        <button className="button-secondary mt-4" onClick={() => void query.refetch()}><RotateCw aria-hidden="true" className="size-4" />Retry {name.toLowerCase()}</button>
      </div>
    </div>
  }
  if (query.isPending || query.isFetching) return <div className="analytics-state min-h-32" role="status" aria-live="polite">
    <p className="flex items-center gap-2 text-sm text-slate-400"><LoaderCircle aria-hidden="true" className="size-4 animate-spin text-emerald-400 motion-reduce:animate-none" />
      {query.isPending ? 'Loading' : 'Refreshing'} {name.toLowerCase()}…</p>
    <div className="mt-5 h-3 w-2/3 animate-pulse rounded bg-slate-800 motion-reduce:animate-none" />
    <div className="mt-3 h-3 w-1/3 animate-pulse rounded bg-slate-800 motion-reduce:animate-none" />
  </div>
  return children
}

export function TeamBadge({ trackId, assignments }: { trackId: number; assignments: TeamAssignment[] | undefined }) {
  if (!assignments) return <span className="text-sm text-slate-400">Team unavailable</span>
  const team = assignments.find((row) => row.track_id === trackId)?.effective_team ?? 'unknown'
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${TEAM_TONES[team].badge}`}>
    <span aria-hidden="true" className={`size-1.5 rounded-full ${TEAM_TONES[team].dot}`} />{TEAM_LABELS[team]}</span>
}

const unavailable = (value: ReactNode) => value === 'Unavailable' || value === 'Checking…'

/** A metric tile. The label (dt) is always followed directly by its value (dd). */
export function Metric({ label, value, hint, icon: Icon }: { label: string; value: ReactNode; hint?: string; icon?: LucideIcon }) {
  return <div className="min-w-0 rounded-xl border border-line bg-canvas/40 p-4">
    <dt className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-400">{Icon && <Icon aria-hidden="true" className="size-3.5 shrink-0 text-slate-500" />}{label}</dt>
    <dd className={`mt-2 break-words font-semibold tabular-nums tracking-tight ${unavailable(value) ? 'text-base text-slate-500' : 'text-xl text-slate-50'}`}>{value}</dd>
    {hint && <p className="mt-2 text-xs leading-5 text-slate-400">{hint}</p>}
  </div>
}

/** A compact label/value row for dense comparisons; use inside a divided dl. */
export function MetricRow({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return <div className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 gap-y-1 py-3">
    <dt className="text-sm text-slate-300">{label}</dt>
    <dd className={`text-right text-sm font-semibold tabular-nums ${unavailable(value) ? 'font-medium text-slate-500' : 'text-slate-50'}`}>{value}</dd>
    {hint && <p className="col-span-2 text-xs leading-5 text-slate-500">{hint}</p>}
  </div>
}
