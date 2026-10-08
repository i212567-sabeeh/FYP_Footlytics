import { StatusBadge } from '../../components/StatusBadge'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { ApiError, apiRequest } from '../../api/client'
import { jobsKey } from '../media/api'
import { isActiveJob, JOB_LABELS, JOB_STATUS_LABELS, type ProcessingJob } from '../media/types'

type AnalyticsJob = 'player_analytics' | 'team_tactical_analytics'
const JOBS: AnalyticsJob[] = ['player_analytics', 'team_tactical_analytics']

export function AnalyticsJobs({ matchId, jobs, canManage, trajectoriesReady, assignmentsReady }: {
  matchId: number; jobs: ProcessingJob[]; canManage: boolean; trajectoriesReady: boolean; assignmentsReady: boolean
}) {
  const client = useQueryClient()
  const active = jobs.some(isActiveJob)
  const action = useMutation({
    mutationFn: ({ type, retryId }: { type: AnalyticsJob; retryId?: number }) => apiRequest<ProcessingJob>(retryId !== undefined
      ? `jobs/${retryId}/retry` : `matches/${matchId}/jobs/${type.replaceAll('_', '-')}`, { method: 'POST' }),
    onSettled: () => client.invalidateQueries({ queryKey: jobsKey(matchId) }),
  })
  const error = action.error instanceof ApiError && action.error.status === 503
    ? 'The processing queue is unavailable. Restore the queue and retry the failed job.' : action.error?.message
  return <section className="panel" aria-labelledby="analytics-processing-heading">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="analytics-processing-heading" className="text-xl font-semibold">Analytics processing</h2>
      <Link className="record-link text-sm" to={`/matches/${matchId}`}>All match processing</Link></div>
    <p className="mt-2 text-sm leading-6 text-slate-400">Generation runs in the background. Visiting this page never starts a job. Published results remain available while a new attempt runs.</p>
    {!trajectoriesReady && <p className="mt-3 text-sm text-amber-200">Current trajectory cleaning must be completed first. Complete the prerequisite processing before generating analytics.</p>}
    {trajectoriesReady && !assignmentsReady && <p className="mt-3 text-sm text-amber-200">Current team assignments are required before team tactical analytics. Complete team classification first.</p>}
    {!canManage && <p className="mt-3 text-sm text-slate-400">Read-only analytics. Generating results requires an editable match and an Admin, Coach or Analyst role.</p>}
    {error && <p className="mt-3 text-sm text-red-300" role="alert">{error}</p>}
    {jobs.filter((job) => isActiveJob(job) && !JOBS.includes(job.job_type as AnalyticsJob)).map((job) => <p key={job.id} className="mt-4 text-sm text-sky-200" role="status">{JOB_LABELS[job.job_type]} is {JOB_STATUS_LABELS[job.status].toLowerCase()} · {job.current_stage?.replaceAll('_', ' ')} · {job.progress_percent}%</p>)}
    <div className="mt-5 grid gap-5 md:grid-cols-2">{JOBS.map((type) => {
      const latest = jobs.find((job) => job.job_type === type)
      const disabled = active || action.isPending || !trajectoriesReady || (type === 'team_tactical_analytics' && !assignmentsReady)
      return <article key={type} className="rounded-lg border border-slate-800 p-4" aria-label={`${JOB_LABELS[type]} processing`}>
        <h3 className="font-medium">{JOB_LABELS[type]}</h3>
        {latest ? <div className="mt-3 text-sm leading-6 text-slate-300">
          <p>Job #{latest.id} · <StatusBadge status={latest.status} /> · {latest.progress_percent}%</p>
          <p>Stage: {latest.current_stage?.replaceAll('_', ' ') || 'Not started'}</p>
          {isActiveJob(latest) && <progress aria-label={`${JOB_LABELS[type]} progress`} className="mt-3 h-2 w-full accent-emerald-400" max={100} value={latest.progress_percent} />}
          {latest.error_message && <p className="mt-2 break-words text-red-300">{latest.error_message}</p>}
          {latest.warning_message && <p className="mt-2 break-words text-amber-200">{latest.warning_message}</p>}
        </div> : <p className="mt-3 text-sm text-slate-400">No recent {JOB_LABELS[type].toLowerCase()} job.</p>}
        {canManage && <div className="mt-4 flex flex-wrap gap-3"><button className="button-primary" disabled={disabled} onClick={() => action.mutate({ type })}>
          {action.isPending && action.variables.type === type ? 'Submitting…' : type === 'player_analytics' ? 'Generate Player Analytics' : 'Generate Team Tactical Analytics'}</button>
          {latest && ['failed', 'cancelled'].includes(latest.status) && <button className="button-secondary" aria-label={`Retry ${JOB_LABELS[type]} job ${latest.id}`} disabled={disabled} onClick={() => action.mutate({ type, retryId: latest.id })}>Retry</button>}
        </div>}
      </article>
    })}</div>
  </section>
}
