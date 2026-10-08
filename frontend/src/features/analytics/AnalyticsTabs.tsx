import { useRef, type KeyboardEvent } from 'react'
import { Activity, Flame, LayoutDashboard, Network, Tags } from 'lucide-react'

const ANALYTICS_TABS = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'players', label: 'Players', icon: Activity },
  { key: 'tactics', label: 'Team Tactics', icon: Network },
  { key: 'heatmap', label: 'Heatmap', icon: Flame },
  { key: 'assignments', label: 'Team Assignments', icon: Tags },
] as const
export type AnalyticsTab = typeof ANALYTICS_TABS[number]['key']

/**
 * WAI-ARIA tabs with automatic activation (arrows, Home and End move and
 * select). The bar stays below the top bar while long sections scroll.
 */
export function AnalyticsTabs({ tab, onChange }: { tab: AnalyticsTab; onChange: (tab: AnalyticsTab) => void }) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([])
  function keyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = ANALYTICS_TABS.length - 1
    const next = event.key === 'ArrowRight' ? (index === last ? 0 : index + 1) : event.key === 'ArrowLeft' ? (index === 0 ? last : index - 1)
      : event.key === 'Home' ? 0 : event.key === 'End' ? last : null
    if (next === null) return
    event.preventDefault(); onChange(ANALYTICS_TABS[next]!.key); buttons.current[next]?.focus()
  }
  return <div className="sticky top-16 z-20 -mx-4 border-b border-line bg-canvas/90 px-4 backdrop-blur-md sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
    <div className="flex gap-1 overflow-x-auto py-2 [scrollbar-width:thin]" role="tablist" aria-label="Match analytics sections">
      {ANALYTICS_TABS.map(({ key, label, icon: Icon }, index) => {
        const active = tab === key
        return <button key={key} id={`analytics-tab-${key}`} type="button" role="tab" aria-selected={active} aria-controls={`analytics-panel-${key}`}
          tabIndex={active ? 0 : -1} ref={(element) => { buttons.current[index] = element }} onClick={() => onChange(key)} onKeyDown={(event) => keyDown(event, index)}
          className={`relative inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${active
            ? 'bg-emerald-400/10 text-emerald-100' : 'text-slate-400 hover:bg-surface-raised/70 hover:text-slate-100'}`}>
          <Icon aria-hidden="true" className={`size-4 shrink-0 ${active ? 'text-emerald-300' : 'text-slate-500'}`} />{label}
          {active && <span aria-hidden="true" className="absolute inset-x-3 -bottom-2 h-0.5 rounded-full bg-emerald-400" />}
        </button>
      })}
    </div>
  </div>
}
