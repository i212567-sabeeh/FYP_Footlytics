import { StatusBadge } from '../../components/StatusBadge'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import { jobVersion } from '../analytics/api'
import { jobsKey } from '../media/api'
import { isActiveJob, type ProcessingJob } from '../media/types'
import { downloadReportFile, reportKey, type DownloadKind, type ReportStatus } from './api'

export function ReportsPanel({ matchId, version, jobs, canManage, playersReady, teamsReady }: {
  matchId: number; version: string; jobs: ProcessingJob[]; canManage: boolean; playersReady: boolean; teamsReady: boolean
}) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: [...reportKey(matchId), version, jobVersion(jobs, ['match_report'])], gcTime: 0,
    queryFn: ({ signal }) => apiRequest<ReportStatus>(`matches/${matchId}/report`, { signal }) })
  const latest = jobs.find((job) => job.job_type === 'match_report')
  const active = jobs.some(isActiveJob)
  const status = query.isSuccess && !query.isFetching ? query.data : undefined
  const generate = useMutation({ mutationFn: (retryId?: number) => apiRequest<ProcessingJob>(retryId === undefined
    ? `matches/${matchId}/jobs/match-report` : `jobs/${retryId}/retry`, { method: 'POST' }),
    onSettled: () => Promise.all([client.invalidateQueries({ queryKey: jobsKey(matchId) }), client.invalidateQueries({ queryKey: reportKey(matchId) })]),
  })
  const download = useMutation({ mutationFn: (kind: DownloadKind) => downloadReportFile(matchId, kind),
    onError: () => client.invalidateQueries({ queryKey: reportKey(matchId) }),
  })
  return <section className="panel" aria-labelledby="reports-heading">
    <h2 id="reports-heading" className="text-xl font-semibold">Reports / Exports</h2>
    <p className="mt-2 text-sm leading-6 text-slate-400">Download a Match PDF or current analytics summaries. Reports use saved results; unavailable analytics are labeled in the PDF.</p>
    {query.isPending || query.isFetching ? <p className="mt-3 text-sm" role="status">Checking report…</p> : null}
    {query.error && <p className="mt-3 text-sm text-red-300" role="alert">Could not load report status. {query.error.message}</p>}
    {status && !status.available && !status.stale && <p className="mt-3 text-sm text-slate-300">No report generated yet.</p>}
    {status?.stale && <p className="mt-3 text-sm text-amber-200"><StatusBadge status="stale" /> Analytics have changed. Regenerate the report to include current results.</p>}
    {status?.current && status.summary && <p className="mt-3 text-sm text-emerald-300">Current report · {status.summary.page_count} pages · Generated {new Date(status.summary.generated_at).toLocaleString()}</p>}
    {latest && <div className="mt-4 text-sm leading-6 text-slate-300" aria-label="PDF report job">
      <p>PDF report: <StatusBadge status={latest.status} /> · {latest.current_stage?.replaceAll('_', ' ') || 'Queued'} · {latest.progress_percent}%</p>
      {isActiveJob(latest) && <progress className="mt-2 h-2 w-full accent-emerald-400" aria-label="PDF report progress" value={latest.progress_percent} max={100} />}
      {latest.error_message && <p className="break-words text-red-300">{latest.error_message}</p>}
      {latest.warning_message && <p className="break-words text-amber-200">{latest.warning_message}</p>}
    </div>}
    {(generate.error || download.error) && <p className="mt-3 break-words text-sm text-red-300" role="alert">{generate.error?.message || download.error?.message}</p>}
    {!canManage && <p className="mt-3 text-sm text-slate-400">Read-only reports and exports. Generation requires an editable Match and an Admin, Coach or Analyst role.</p>}
    <div className="mt-5 flex flex-wrap gap-3">
      {canManage && <button className="button-primary" disabled={active || generate.isPending} onClick={() => generate.mutate(undefined)}>{generate.isPending ? 'Submitting…' : 'Generate PDF Report'}</button>}
      {canManage && latest && ['failed', 'cancelled'].includes(latest.status) && <button className="button-secondary" disabled={active || generate.isPending} onClick={() => generate.mutate(latest.id)}>Retry PDF Report</button>}
      <button className="button-secondary" disabled={!status?.current || download.isPending} onClick={() => download.mutate('report')}>Download PDF Report</button>
      <button className="button-secondary" disabled={!playersReady || download.isPending} onClick={() => download.mutate('player-analytics')}>Download Player Analytics CSV</button>
      <button className="button-secondary" disabled={!teamsReady || download.isPending} onClick={() => download.mutate('team-analytics')}>Download Team Analytics CSV</button>
    </div>
    {download.isPending && <p className="mt-3 text-sm" role="status">Preparing download…</p>}
    {(!playersReady || !teamsReady) && <p className="mt-3 text-sm text-slate-400">CSV downloads require the corresponding current analytics result.</p>}
  </section>
}
