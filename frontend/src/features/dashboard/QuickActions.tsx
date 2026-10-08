import { ArrowRight, ChartColumnBig, CirclePlus, Goal, Shirt, UserPlus, Users, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router'
import { useCapabilities } from '../football/hooks'
import type { FootballMatch } from '../football/types'

interface Action { to: string; label: string; description: string; icon: LucideIcon }

/** Role-aware shortcuts. Each uses the capability behind the matching page
 * action or route guard, so users only see workflows they may perform. */
export function QuickActions({ labelledBy, latestMatch }: { labelledBy: string; latestMatch: FootballMatch | undefined }) {
  const can = useCapabilities()
  const actions: Action[] = []
  if (can.match) actions.push({ to: '/matches/new', label: 'Create match', description: 'Set teams, date and pitch dimensions', icon: CirclePlus })
  actions.push({ to: '/matches', label: 'Open matches', description: 'Browse and filter accessible matches', icon: Goal })
  if (can.analytics && latestMatch) {
    // Opens the newest match's analytics page, which states what is available.
    actions.push({ to: `/matches/${latestMatch.id}/analytics`, label: 'Latest match analytics', description: latestMatch.title, icon: ChartColumnBig })
  }
  if (can.roster) {
    actions.push({ to: '/teams', label: 'Manage teams', description: 'Teams, squads and roster history', icon: Users },
      { to: '/players', label: 'Manage players', description: 'Player profiles and linked accounts', icon: Shirt })
  }
  if (can.admin) actions.push({ to: '/admin/signup-requests', label: 'Review access requests', description: 'Approve or reject account requests', icon: UserPlus })
  return <ul aria-labelledby={labelledBy} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
    {actions.map(({ to, label, description, icon: Icon }) => <li key={to}>
      <Link to={to} className="group flex h-full items-center gap-3 rounded-xl border border-line bg-canvas/40 p-3.5 transition-colors hover:border-emerald-400/30 hover:bg-surface-raised">
        <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-lg bg-surface-raised text-emerald-300 ring-1 ring-inset ring-line-strong transition-colors group-hover:ring-emerald-400/30">
          <Icon className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-slate-100">{label}</span>
          <span className="block truncate text-xs text-slate-400">{description}</span>
        </span>
        <ArrowRight aria-hidden="true" className="size-4 shrink-0 text-slate-500 transition group-hover:translate-x-0.5 group-hover:text-emerald-300" />
      </Link>
    </li>)}
  </ul>
}
