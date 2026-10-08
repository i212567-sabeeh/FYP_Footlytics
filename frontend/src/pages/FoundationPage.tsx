import { Goal, Shield, Shirt, Users } from 'lucide-react'
import { StatCard } from '../components/StatCard'
import { roleLabel } from '../features/auth/types'
import { useLatestJobs } from '../features/dashboard/api'
import { ProcessingOverview } from '../features/dashboard/ProcessingOverview'
import { QuickActions } from '../features/dashboard/QuickActions'
import { RecentMatches } from '../features/dashboard/RecentMatches'
import { useRecords } from '../features/football/api'
import { useCapabilities } from '../features/football/hooks'
import type { FootballMatch } from '../features/football/types'
import { useAuth } from '../hooks/useAuth'

const LATEST_MATCHES = 5

/** Decorative pitch outline behind the welcome panel. */
function PitchLines() {
  return <svg aria-hidden="true" viewBox="0 0 210 136" className="pointer-events-none absolute -right-12 -top-8 hidden h-64 text-emerald-400/10 lg:block">
    <g fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="1" y="1" width="208" height="134" rx="2" />
      <path d="M105 1v134" />
      <circle cx="105" cy="68" r="18" />
      <rect x="1" y="34" width="33" height="68" />
      <rect x="176" y="34" width="33" height="68" />
    </g>
  </svg>
}

export function FoundationPage() {
  const { user } = useAuth()
  const can = useCapabilities()
  const clubs = useRecords<unknown>('clubs', { limit: 1 })
  const teams = useRecords<unknown>('teams', { limit: 1 })
  const players = useRecords<unknown>('players', { limit: 1 })
  // The match API orders by match date, newest first, so one small page gives
  // both the KPI total and the genuinely latest matches.
  const matches = useRecords<FootballMatch>('matches', { limit: LATEST_MATCHES })
  const latest = matches.data?.items ?? []
  const jobs = useLatestJobs(latest.map((match) => match.id), can.analytics)
  const totals = [
    ['/clubs', 'Clubs', Shield, clubs], ['/teams', 'Teams', Users, teams],
    ['/players', 'Players', Shirt, players], ['/matches', 'Matches', Goal, matches],
  ] as const

  return <section aria-labelledby="page-title" className="space-y-8">
    <header className="relative overflow-hidden rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-8">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgb(60_203_127/0.14),transparent_60%)]" />
      <PitchLines />
      <div className="relative max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-400">Football video analytics</p>
        <h1 id="page-title" className="mt-3 text-3xl font-semibold tracking-tight text-balance text-slate-50 sm:text-4xl">Welcome, {user?.full_name}</h1>
        <p className="mt-4 leading-7 text-slate-300">Open a match to review its video and available analysis. Match tools include pitch calibration, detection and tracking review, player and team analytics, PDF reports and CSV exports. Available actions depend on your role and completed processing.</p>
        <p className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-400">
          Signed in as
          {user?.roles.map((role) => <span key={role} className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-2.5 py-0.5 font-medium text-emerald-200">{roleLabel(role)}</span>)}
        </p>
      </div>
      <div className="relative mt-8 border-t border-line pt-6">
        <h2 id="quick-actions-heading" className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Quick actions</h2>
        <QuickActions labelledBy="quick-actions-heading" latestMatch={latest[0]} />
      </div>
    </header>

    <section aria-labelledby="totals-heading">
      <h2 id="totals-heading" className="sr-only">Record totals</h2>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {totals.map(([to, label, icon, query]) => <StatCard key={to} to={to} label={label} icon={icon} value={query.data?.total} error={Boolean(query.error)} />)}
      </div>
      <p className="mt-3 text-xs text-slate-500">Counts include all records you can access, including inactive or archived records.</p>
    </section>

    <div className={`grid items-start gap-6 ${can.analytics ? 'xl:grid-cols-3' : ''}`}>
      <RecentMatches className={can.analytics ? 'xl:col-span-2' : ''} query={matches} jobs={can.analytics ? jobs : undefined} showAnalytics={can.analytics} />
      {can.analytics && <ProcessingOverview matches={matches} jobs={jobs} />}
    </div>
  </section>
}
