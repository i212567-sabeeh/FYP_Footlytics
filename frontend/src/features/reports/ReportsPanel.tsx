import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileSpreadsheet, FileText, LoaderCircle, Lock, Play, RotateCw } from 'lucide-react'
import { StatusBadge } from '../../components/StatusBadge'
import { apiRequest } from '../../api/client'
import { jobVersion } from '../analytics/api'
import type { Availability } from '../analytics/results'
import { AvailabilityBadge, Note } from '../analytics/ResultState'
import { jobsKey } from '../media/api'
import { isActiveJob, type ProcessingJob } from '../media/types'
import { downloadReportFile, reportKey, type DownloadKind, type ReportStatus } from './api'

function fileSize(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

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
  const reportState: Availability = query.error ? 'error' : !status ? 'checking' : status.current ? 'available' : status.stale ? 'stale' : 'missing'
  const downloadIcon = (kind: DownloadKind) => download.isPending && download.variables === kind
    ? <LoaderCircle aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" /> : <Download aria-hidden="true" className="size-4" />
  const exports = [
    ['player-analytics', 'Player analytics CSV', 'Per-track physical metrics from the current player analytics result.', playersReady, 'Download Player Analytics CSV'],
    ['team-analytics', 'Team analytics CSV', 'Team geometry summaries from the current team tactical result.', teamsReady, 'Download Team Analytics CSV'],
  ] as const
  return <section className="panel" aria-labelledby="reports-heading">
    <h2 id="reports-heading" className="flex items-center gap-2 text-xl font-semibold"><FileText aria-hidden="true" className="size-5 text-emerald-300" />Reports / Exports</h2>
    <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">Download a Match PDF or current analytics summaries. Reports use saved results; unavailable analytics are labeled in the PDF.</p>
    {!canManage && <Note icon={Lock}>Read-only reports and exports. Generation requires an editable Match and an Admin, Coach or Analyst role.</Note>}
    <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <article className="flex min-w-0 flex-col rounded-xl border border-line bg-canvas/40 p-5" aria-labelledby="pdf-report-heading">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 id="pdf-report-heading" className="flex items-center gap-2 font-semibold"><FileText aria-hidden="true" className="size-4 text-emerald-300" />Match PDF report</h3>
          <AvailabilityBadge state={reportState} />
        </div>
        <div className="mt-3 space-y-2 text-sm">
          {query.isPending || query.isFetching ? <p className="text-slate-400" role="status">Checking report…</p> : null}
          {query.error && <p className="text-red-300" role="alert">Could not load report status. {query.error.message}</p>}
          {status && !status.available && !status.stale && <p className="text-slate-300">No report generated yet.</p>}
          {status?.stale && <p className="text-amber-200">Analytics have changed. Regenerate the report to include current results.</p>}
          {status?.current && status.summary && <p className="text-emerald-300">Current report · {status.summary.page_count} pages · Generated {new Date(status.summary.generated_at).toLocaleString()}</p>}
        </div>
        {status?.current && status.summary && <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          {[['File size', fileSize(status.summary.size_bytes)], ['Player rows', status.summary.player_rows], ['Team rows', status.summary.team_rows], ['Heatmaps', status.summary.heatmaps]].map(([label, value]) =>
            <div key={label} className="rounded-lg border border-line bg-surface/60 px-3 py-2"><dt className="text-xs text-slate-400">{label}</dt><dd className="mt-0.5 font-semibold tabular-nums text-slate-100">{value}</dd></div>)}
        </dl>}
        {latest && <div className="mt-4 rounded-lg border border-line bg-surface/60 p-3 text-sm" role="group" aria-label="PDF report job">
          <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-slate-300">Latest generation · Job #{latest.id}</span><StatusBadge status={latest.status} /></div>
          <p className="mt-2 tabular-nums text-slate-400">{latest.current_stage?.replaceAll('_', ' ') || 'Queued'} · {latest.progress_percent}%</p>
          {isActiveJob(latest) && <progress className="progress-bar mt-2" aria-label="PDF report progress" value={latest.progress_percent} max={100} />}
          {latest.error_message && <p className="mt-2 break-words text-red-300">{latest.error_message}</p>}
          {latest.warning_message && <p className="mt-2 break-words text-amber-200">{latest.warning_message}</p>}
        </div>}
        <div className="mt-auto flex flex-wrap gap-2 pt-5">
          {canManage && <button className="button-primary" disabled={active || generate.isPending} onClick={() => generate.mutate(undefined)}>
            <Play aria-hidden="true" className="size-4" />{generate.isPending ? 'Submitting…' : 'Generate PDF Report'}</button>}
          {canManage && latest && ['failed', 'cancelled'].includes(latest.status) && <button className="button-secondary" disabled={active || generate.isPending} onClick={() => generate.mutate(latest.id)}>
            <RotateCw aria-hidden="true" className="size-4" />Retry PDF Report</button>}
          <button className="button-secondary" disabled={!status?.current || download.isPending} onClick={() => download.mutate('report')}>{downloadIcon('report')}Download PDF Report</button>
        </div>
      </article>
      <article className="min-w-0 rounded-xl border border-line bg-canvas/40 p-5" aria-labelledby="exports-heading">
        <h3 id="exports-heading" className="flex items-center gap-2 font-semibold"><FileSpreadsheet aria-hidden="true" className="size-4 text-emerald-300" />Data exports</h3>
        <ul className="mt-2 divide-y divide-line">{exports.map(([kind, title, detail, ready, label]) => <li key={kind} className="flex flex-col items-start gap-3 py-4">
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-2 font-medium text-slate-100">{title}
              {ready ? <AvailabilityBadge state="available" /> : <span className="text-xs font-normal text-slate-500">Needs current analytics</span>}</p>
            <p className="mt-1 text-xs leading-5 text-slate-400">{detail}</p>
          </div>
          <button className="button-secondary shrink-0" disabled={!ready || download.isPending} onClick={() => download.mutate(kind)}>{downloadIcon(kind)}{label}</button>
        </li>)}</ul>
        {(!playersReady || !teamsReady) && <p className="mt-1 text-sm text-slate-400">CSV downloads require the corresponding current analytics result.</p>}
      </article>
    </div>
    {download.isPending && <p className="mt-4 text-sm text-slate-300" role="status">Preparing download…</p>}
    {(generate.error || download.error) && <p className="mt-4 break-words text-sm text-red-300" role="alert">{generate.error?.message || download.error?.message}</p>}
  </section>
}
