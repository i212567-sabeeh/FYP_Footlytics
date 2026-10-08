import { useState, type InputHTMLAttributes, type ReactNode } from 'react'
import { Crosshair, Eye, EyeOff, FileText, ScanSearch } from 'lucide-react'
import { BrandMark } from '../../components/BrandMark'

const FEATURES = [
  [ScanSearch, 'Player detection and tracking', 'YOLO person detection and ByteTrack tracking on recorded match video.'],
  [Crosshair, 'Pitch calibration', 'Map camera pixels to pitch metres for positions, movement and team shape.'],
  [FileText, 'Analytics and reports', 'Player metrics, team tactics, heatmaps, PDF reports and CSV exports.'],
] as const

/** Sign-in and sign-up frame: product context beside the form (stacked on small screens). */
export function AuthCard({ eyebrow, title, intro, children, footer }: { eyebrow: string; title: string; intro: string; children: ReactNode; footer: ReactNode }) {
  return <div className="mx-auto grid max-w-5xl overflow-hidden rounded-2xl border border-line bg-surface shadow-card lg:grid-cols-[1.05fr_1fr]">
    <aside className="relative hidden overflow-hidden border-r border-line bg-canvas p-10 lg:block">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgb(60_203_127/0.16),transparent_60%)]" />
      <div className="relative"><BrandMark /></div>
      <p className="relative mt-10 text-2xl font-semibold leading-snug tracking-tight text-slate-50">Post-match football analysis from recorded video.</p>
      <ul className="relative mt-8 space-y-5">{FEATURES.map(([Icon, name, text]) => <li key={name} className="flex gap-3">
        <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-lg bg-emerald-400/10 text-emerald-300 ring-1 ring-emerald-400/25"><Icon className="size-4" /></span>
        <div><p className="font-medium text-slate-100">{name}</p><p className="mt-0.5 text-sm text-slate-400">{text}</p></div>
      </li>)}</ul>
      <p className="relative mt-10 text-xs text-slate-500">Accounts are created or approved by an administrator.</p>
    </aside>
    <section className="p-6 sm:p-10">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300">{eyebrow}</p>
      <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-50 sm:text-3xl">{title}</h1>
      <p className="mt-3 text-sm leading-6 text-slate-400">{intro}</p>
      {children}
      <div className="mt-6 border-t border-line pt-5 text-sm text-slate-400">{footer}</div>
    </section>
  </div>
}

/** A password input with an explicit show/hide toggle; the value never leaves the field. */
export function PasswordInput({ toggleLabel = 'password', ...props }: InputHTMLAttributes<HTMLInputElement> & { toggleLabel?: string }) {
  const [visible, setVisible] = useState(false)
  return <div className="relative">
    <input {...props} type={visible ? 'text' : 'password'} className="field-input pr-12" />
    <button type="button" className="absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-lg text-slate-400 transition-colors hover:text-slate-100"
      aria-label={`${visible ? 'Hide' : 'Show'} ${toggleLabel}`} aria-pressed={visible} onClick={() => setVisible(!visible)}>
      {visible ? <EyeOff aria-hidden="true" className="size-4" /> : <Eye aria-hidden="true" className="size-4" />}</button>
  </div>
}
