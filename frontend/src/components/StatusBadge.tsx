import { JOB_STATUS_LABELS, type JobStatus } from '../features/media/types'

const COLORS: Record<JobStatus | 'stale' | 'unavailable', string> = {
  queued: 'bg-slate-800 text-slate-200', running: 'bg-sky-950 text-sky-200',
  completed: 'bg-emerald-950 text-emerald-200', completed_with_warnings: 'bg-amber-950 text-amber-200',
  failed: 'bg-red-950 text-red-200', cancelled: 'bg-slate-800 text-slate-400',
  stale: 'bg-amber-950 text-amber-200', unavailable: 'bg-slate-800 text-slate-400',
}
export function StatusBadge({ status }: { status: keyof typeof COLORS }) {
  const label = status === 'stale' ? 'Stale' : status === 'unavailable' ? 'Unavailable' : status === 'running' ? 'Processing' : JOB_STATUS_LABELS[status]
  return <span className={`inline-flex rounded-full px-3 py-1 text-xs font-medium ${COLORS[status]}`}>{label}</span>
}
