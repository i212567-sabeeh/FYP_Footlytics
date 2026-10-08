/** FOOTLYTICS logo: a pitch-outline mark with a wordmark that stays readable to
 * assistive technology when visually compact. */
export function BrandMark({ compact = false }: { compact?: boolean }) {
  return <span className="flex items-center gap-2.5">
    <svg aria-hidden="true" viewBox="0 0 32 32" className="size-8 shrink-0 text-emerald-400">
      <rect width="32" height="32" rx="8" className="fill-emerald-400/10" />
      <g fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="5" y="8" width="22" height="16" rx="1.5" />
        <path d="M16 8v16" />
        <circle cx="16" cy="16" r="3.2" />
      </g>
    </svg>
    <span className={compact ? 'sr-only' : 'text-[15px] font-bold tracking-[0.2em] text-slate-50'}>FOOTLYTICS</span>
  </span>
}
