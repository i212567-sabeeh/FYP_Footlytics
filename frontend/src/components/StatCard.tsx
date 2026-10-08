import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router'

interface Props { to: string; label: string; icon: LucideIcon; value: number | undefined; error: boolean }

/** KPI card for a real backend total: no invented trends or comparisons. */
export function StatCard({ to, label, icon: Icon, value, error }: Props) {
  return <Link to={to} className="panel group flex flex-col gap-4 p-5 transition-colors hover:border-emerald-400/30 hover:bg-surface-raised">
    <span className="flex items-center justify-between gap-3">
      <span className="text-sm font-medium text-slate-400">{label}</span>
      <span aria-hidden="true" className="grid size-9 place-items-center rounded-lg bg-emerald-400/10 text-emerald-300 ring-1 ring-inset ring-emerald-400/20 transition-colors group-hover:bg-emerald-400/15">
        <Icon className="size-[18px]" />
      </span>
    </span>
    {error
      ? <span className="flex flex-col gap-1"><span className="text-lg font-semibold text-slate-200">Unavailable</span><span className="text-xs text-red-300">Open to retry loading.</span></span>
      : <span className="text-3xl font-semibold tabular-nums tracking-tight text-slate-50">{value ?? '…'}</span>}
  </Link>
}
