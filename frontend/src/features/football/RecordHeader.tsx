import type { ReactNode } from 'react'
import { ArrowLeft, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router'
import { Initials } from './ui'

/** Header for club, team and player detail pages, matching the match workspace headers. */
export function RecordHeader({ eyebrow, icon: Icon, title, badges, back, actions, children }: {
  eyebrow: string; icon: LucideIcon; title: string; badges?: ReactNode; back: { to: string; label: string }; actions?: ReactNode; children?: ReactNode
}) {
  return <header className="relative mb-6 overflow-hidden rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-7">
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgb(60_203_127/0.12),transparent_60%)]" />
    <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <div className="flex min-w-0 items-start gap-4">
        <Initials name={title} className="size-12 text-base" />
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300"><Icon aria-hidden="true" className="size-4" />{eyebrow}</p>
          <h1 className="mt-1.5 break-words text-2xl font-semibold tracking-tight text-slate-50 sm:text-3xl">{title}</h1>
          {badges && <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">{badges}</div>}
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
        <Link className="button-secondary" to={back.to}><ArrowLeft aria-hidden="true" className="size-4" />{back.label}</Link>
        {actions}
      </div>
    </div>
    {children && <div className="relative mt-6 border-t border-line pt-5">{children}</div>}
  </header>
}

export function Chip({ children }: { children: ReactNode }) {
  return <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line-strong px-2.5 py-0.5 font-medium text-slate-300">{children}</span>
}
