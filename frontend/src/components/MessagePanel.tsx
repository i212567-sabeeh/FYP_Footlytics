import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

const TONES = {
  neutral: 'bg-slate-500/10 text-slate-300 ring-slate-500/40',
  warning: 'bg-amber-400/10 text-amber-200 ring-amber-400/40',
  danger: 'bg-red-400/10 text-red-200 ring-red-400/40',
} as const

/** A centred page-level message (access denied, not found, session problems). */
export function MessagePanel({ icon: Icon, title, tone = 'neutral', children, actions }: {
  icon: LucideIcon; title: string; tone?: keyof typeof TONES; children: ReactNode; actions?: ReactNode
}) {
  return <section className="mx-auto mt-4 max-w-xl rounded-2xl border border-line bg-surface p-8 text-center shadow-card sm:p-10">
    <span aria-hidden="true" className={`mx-auto grid size-12 place-items-center rounded-full ring-1 ${TONES[tone]}`}><Icon className="size-6" /></span>
    <h1 className="mt-5 text-2xl font-semibold tracking-tight text-slate-50">{title}</h1>
    <div className="mt-3 text-slate-300">{children}</div>
    {actions && <div className="mt-6 flex flex-wrap justify-center gap-3">{actions}</div>}
  </section>
}
