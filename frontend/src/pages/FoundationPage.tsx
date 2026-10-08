import { useAuth } from '../hooks/useAuth'
import { roleLabel } from '../features/auth/types'
import { Link } from 'react-router'
import { useRecords } from '../features/football/api'

export function FoundationPage() {
  const { user } = useAuth()
  return (
    <section aria-labelledby="page-title">
      <p className="mb-4 text-sm font-semibold uppercase tracking-widest text-emerald-400">
        Football video analytics
      </p>
      <h1 id="page-title" className="text-4xl font-semibold tracking-tight sm:text-5xl">
        Welcome, {user?.full_name}
      </h1>
      <p className="mt-6 text-lg leading-8 text-slate-300">
        Role(s): {user?.roles.map(roleLabel).join(', ')}
      </p>
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {['clubs', 'teams', 'players', 'matches'].map((resource) => <CountCard key={resource} resource={resource} />)}
      </div>
      <p className="mt-3 text-sm text-slate-500">Counts include all records you can access, including inactive or archived records.</p>
      <div className="mt-10 rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h2 className="text-lg font-medium">Your account is ready</h2>
        <p className="mt-2 leading-7 text-slate-400">
          Open a match to review its video and available analysis. Match tools include
          pitch calibration, detection and tracking review, player and team analytics,
          PDF reports and CSV exports. Available actions depend on your role and
          completed processing.
        </p>
      </div>
    </section>
  )
}

function CountCard({ resource }: { resource: string }) {
  const records = useRecords<unknown>(resource, { limit: 1 })
  return <Link className="panel block hover:border-emerald-800" to={`/${resource}`}>
    <span className="text-sm capitalize text-slate-400">{resource}</span>
    <span className="mt-3 block text-3xl font-semibold">{records.error ? 'Unavailable' : records.data ? records.data.total : '…'}</span>
    {records.error && <span className="mt-2 block text-xs text-red-300">Open to retry loading.</span>}
  </Link>
}
