import { CircleCheck, CircleDashed, CircleSlash, CircleX, Clock3, LoaderCircle, RefreshCw, TriangleAlert, type LucideIcon } from 'lucide-react'
import { JOB_STATUS_LABELS, type JobStatus } from '../features/media/types'

const STYLES: Record<JobStatus | 'stale' | 'unavailable', [string, LucideIcon]> = {
  queued: ['border-slate-500/40 bg-slate-500/10 text-slate-200', Clock3],
  running: ['border-sky-400/35 bg-sky-400/10 text-sky-200', LoaderCircle],
  completed: ['border-emerald-400/35 bg-emerald-400/10 text-emerald-200', CircleCheck],
  completed_with_warnings: ['border-amber-400/35 bg-amber-400/10 text-amber-200', TriangleAlert],
  failed: ['border-red-400/35 bg-red-400/10 text-red-200', CircleX],
  cancelled: ['border-slate-500/40 bg-slate-500/10 text-slate-400', CircleSlash],
  stale: ['border-amber-400/35 bg-amber-400/10 text-amber-200', RefreshCw],
  unavailable: ['border-slate-500/40 bg-slate-500/10 text-slate-400', CircleDashed],
}
export function StatusBadge({ status }: { status: keyof typeof STYLES }) {
  const label = status === 'stale' ? 'Stale' : status === 'unavailable' ? 'Unavailable' : status === 'running' ? 'Processing' : JOB_STATUS_LABELS[status]
  const [style, Icon] = STYLES[status]
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${style}`}>
    <Icon aria-hidden="true" className={`size-3.5 shrink-0${status === 'running' ? ' animate-spin motion-reduce:animate-none' : ''}`} />{label}
  </span>
}
