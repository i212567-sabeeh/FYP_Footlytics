import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Activity, ArrowRight, Lock, Network, Play, RotateCw, TriangleAlert, Workflow, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router'
import { StatusBadge } from '../../components/StatusBadge'
import { ApiError, apiRequest } from '../../api/client'
import { jobsKey } from '../media/api'
import { isActiveJob, JOB_LABELS, JOB_STATUS_LABELS, type ProcessingJob } from '../media/types'
import type { Availability } from './results'
import { AvailabilityBadge, Note } from './ResultState'

type AnalyticsJob = 'player_analytics' | 'team_tactical_analytics'
const JOBS: readonly [AnalyticsJob, LucideIcon][] = [['player_analytics', Activity], ['team_tactical_analytics', Network]]

export function AnalyticsJobs({ matchId, jobs, canManage, trajectoriesReady, assignmentsReady, outputs }: {
  matchId: number; jobs: ProcessingJob[]; canManage: boolean; trajectoriesReady: boolean; assignmentsReady: boolean
  outputs: Record<AnalyticsJob, Availability>
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
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 id="analytics-processing-heading" className="flex items-center gap-2 text-xl font-semibold"><Workflow aria-hidden="true" className="size-5 text-emerald-300" />Analytics processing</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">Generation runs in the background. Visiting this page never starts a job. Published results remain available while a new attempt runs.</p>
      </div>
      <Link className="button-secondary" to={`/matches/${matchId}`}>All match processing<ArrowRight aria-hidden="true" className="size-4" /></Link>
    </div>
    {!trajectoriesReady && <Note icon={TriangleAlert} tone="amber">Current trajectory cleaning must be completed first. Complete the prerequisite processing before generating analytics.</Note>}
    {trajectoriesReady && !assignmentsReady && <Note icon={TriangleAlert} tone="amber">Current team assignments are required before team tactical analytics. Complete team classification first.</Note>}
    {!canManage && <Note icon={Lock}>Read-only analytics. Generating results requires an editable match and an Admin, Coach or Analyst role.</Note>}
    {error && <p className="mt-3 break-words text-sm text-red-300" role="alert">{error}</p>}
    {jobs.filter((job) => isActiveJob(job) && !JOBS.some(([type]) => type === job.job_type)).map((job) => <p key={job.id} className="mt-4 text-sm text-sky-200" role="status">
      {JOB_LABELS[job.job_type]} is {JOB_STATUS_LABELS[job.status].toLowerCase()} · {job.current_stage?.replaceAll('_', ' ')} · {job.progress_percent}%</p>)}
    <div className="mt-5 grid gap-4 md:grid-cols-2">{JOBS.map(([type, Icon]) => {
      const latest = jobs.find((job) => job.job_type === type)
      const disabled = active || action.isPending || !trajectoriesReady || (type === 'team_tactical_analytics' && !assignmentsReady)
      return <article key={type} className="flex min-w-0 flex-col rounded-xl border border-line bg-canvas/40 p-5" aria-label={`${JOB_LABELS[type]} processing`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 font-semibold"><Icon aria-hidden="true" className="size-4 text-emerald-300" />{JOB_LABELS[type]}</h3>
          {latest && <StatusBadge status={latest.status} />}
        </div>
        {latest ? <div className="mt-3 space-y-1.5 text-sm leading-6 text-slate-300">
          <p className="tabular-nums text-slate-400">Job #{latest.id} · {latest.progress_percent}% · Retries: {latest.retry_count}</p>
          <p>Stage: {latest.current_stage?.replaceAll('_', ' ') || 'Not started'}</p>
          {isActiveJob(latest) && <progress aria-label={`${JOB_LABELS[type]} progress`} className="progress-bar mt-1" max={100} value={latest.progress_percent} />}
          {latest.error_message && <p className="break-words text-red-300">{latest.error_message}</p>}
          {latest.warning_message && <p className="break-words text-amber-200">{latest.warning_message}</p>}
        </div> : <p className="mt-3 text-sm text-slate-400">No recent {JOB_LABELS[type].toLowerCase()} job.</p>}
        <p className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-4 text-xs text-slate-400">Current output <AvailabilityBadge state={outputs[type]} /></p>
        {canManage && <div className="mt-4 flex flex-wrap gap-2">
          <button className="button-primary" disabled={disabled} onClick={() => action.mutate({ type })}><Play aria-hidden="true" className="size-4" />
            {action.isPending && action.variables.type === type ? 'Submitting…' : type === 'player_analytics' ? 'Generate Player Analytics' : 'Generate Team Tactical Analytics'}</button>
          {latest && ['failed', 'cancelled'].includes(latest.status) && <button className="button-secondary" aria-label={`Retry ${JOB_LABELS[type]} job ${latest.id}`}
            disabled={disabled} onClick={() => action.mutate({ type, retryId: latest.id })}><RotateCw aria-hidden="true" className="size-4" />Retry</button>}
        </div>}
      </article>
    })}</div>
  </section>
}
