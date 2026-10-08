import { useRef, useState } from 'react'
import { useMutation, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { apiRequest, ApiError } from '../../api/client'
import { StatusBadge } from '../../components/StatusBadge'
import type { Page } from '../football/types'
import { DateText, ErrorMessage, Pager, QueryState } from '../football/ui'
import { jobsKey } from './api'
import { isActiveJob, JOB_LABELS, type ProcessingJob } from './types'

interface ProcessingPanelProps {
  matchId: number
  videoId: number | undefined
  canManage: boolean
  hasActiveJob: boolean
  preparation: UseQueryResult<ProcessingJob | null>
  query: UseQueryResult<Page<ProcessingJob>>
  offset: number
  onOffsetChange: (offset: number) => void
}
const succeeded = (job: ProcessingJob | null | undefined) => job?.status === 'completed' || job?.status === 'completed_with_warnings'
const retryable = (job: ProcessingJob | null | undefined) => job?.status === 'failed' || job?.status === 'cancelled'

function JobDetails({ job, videoId, retry, blocked }: { job: ProcessingJob; videoId: number | undefined; retry?: () => void; blocked: boolean }) {
  return <article className="min-w-0 rounded-lg border border-slate-800 p-4" aria-label={`${JOB_LABELS[job.job_type]} job ${job.id}`}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="font-medium">{JOB_LABELS[job.job_type]} <span className="text-sm text-slate-500">#{job.id}</span></h3>
      <StatusBadge status={job.status} />
    </div>
    {job.video_id !== videoId && <p className="mt-2 text-sm text-slate-400">Earlier source video</p>}
    <div className="mt-3 flex flex-wrap justify-between gap-2 text-sm text-slate-300">
      <span>{job.current_stage?.replaceAll('_', ' ') || 'Not started'}</span><span>{job.progress_percent}%</span>
    </div>
    {isActiveJob(job) && <progress className="mt-3 h-2 w-full accent-emerald-400" aria-label={`Job ${job.id} progress`} max={100} value={job.progress_percent} />}
    {job.warning_message && <p className="mt-3 whitespace-pre-wrap break-words text-sm text-amber-200">Warning: {job.warning_message}</p>}
    {job.error_message && <p className="mt-3 whitespace-pre-wrap break-words text-sm text-red-300">Error: {job.error_message}</p>}
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
      <p>Created <DateText value={job.created_at} /> · Retries: {job.retry_count}</p>
      {job.finished_at && <p>Finished <DateText value={job.finished_at} /></p>}
      {retry && <button className="button-secondary" disabled={blocked} aria-label={`Retry job ${job.id}`} onClick={retry}>Retry</button>}
    </div>
  </article>
}

export function ProcessingPanel({ matchId, videoId, canManage, hasActiveJob, preparation, query, offset, onOffsetChange }: ProcessingPanelProps) {
  const client = useQueryClient()
  const [historyOpen, setHistoryOpen] = useState(false)
  const submitting = useRef(false)
  const action = useMutation({
    mutationFn: (retryId: number | null) => apiRequest<ProcessingJob>(retryId === null
      ? `matches/${matchId}/jobs/video-preparation` : `jobs/${retryId}/retry`, { method: 'POST' }),
    onSuccess: (job) => {
      if (job.job_type === 'video_preparation') client.setQueryData([...jobsKey(matchId), 'preparation', videoId], job)
      onOffsetChange(0)
    },
    // Queue failures may already have persisted a failed job; always refresh it.
    onSettled: () => client.invalidateQueries({ queryKey: jobsKey(matchId) }),
  })
  const current = preparation.data?.video_id === videoId ? preparation.data : null
  const preparing = Boolean(current && isActiveJob(current))
  const prepared = succeeded(current)
  const failed = retryable(current)
  const blocked = hasActiveJob || action.isPending || !query.isSuccess || !preparation.isSuccess
  const label = preparing || (action.isPending && (action.variables === null || action.variables === current?.id))
    ? 'Preparing…' : prepared ? 'Video Prepared ✓' : failed ? 'Retry Preparation' : 'Prepare Video'
  const actionError = action.error instanceof ApiError && action.error.status === 503
    ? new Error('The processing queue is unavailable. Try again after the queue service is restored. A failed job can be retried below.') : action.error
  const activeOthers = query.data?.items.filter((job) => job.id !== current?.id && isActiveJob(job)) ?? []
  const history = preparation.isSuccess ? query.data?.items.filter((job) => job.id !== current?.id && !isActiveJob(job)) ?? [] : []

  function submit(retryId: number | null) {
    if (submitting.current || blocked || !canManage) return
    submitting.current = true
    action.mutate(retryId, { onSettled: () => { submitting.current = false } })
  }

  return <section className="panel mt-8 min-w-0" aria-labelledby="processing-heading">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <h2 id="processing-heading" className="text-xl font-semibold">Processing</h2>
      {canManage && <button className="button-primary" disabled={!videoId || blocked || prepared || preparing}
        onClick={() => submit(failed && current ? current.id : null)}>{label}</button>}
    </div>
    <p className="mt-3 text-sm leading-6 text-slate-400">Preparation validates the current video and is needed only once per source. Detection and tracking are available in Player Detection &amp; Tracking Review.</p>
    {!videoId && <p className="mt-3 text-sm text-slate-400">Upload a valid match video before starting preparation.</p>}
    <ErrorMessage error={actionError} />
    {videoId && <QueryState query={preparation} />}
    <QueryState query={query} />
    {current && <div className="mt-5"><JobDetails job={current} videoId={videoId} blocked={blocked} /></div>}
    {activeOthers.map((job) => <div className="mt-4" key={job.id}><JobDetails job={job} videoId={videoId} blocked={blocked} /></div>)}
    {query.data && <>
      {!query.data.items.length && !current && preparation.isSuccess && <p className="mt-5 text-slate-400">No processing jobs yet.</p>}
      {(history.length > 0 || query.data.total > 25) && <details open={historyOpen} onToggle={(event) => setHistoryOpen(event.currentTarget.open)} className="mt-5 rounded-lg border border-slate-800 p-4">
        <summary className="cursor-pointer text-sm font-medium text-slate-300">Processing History</summary>
        <div className="mt-4 space-y-3">{history.map((job) => <JobDetails job={job} key={job.id} videoId={videoId} blocked={blocked}
          retry={canManage && job.job_type !== 'video_preparation' && job.video_id === videoId && retryable(job) ? () => submit(job.id) : undefined} />)}</div>
        {query.data.total > 25 && <Pager total={query.data.total} offset={offset} onChange={onOffsetChange} />}
      </details>}
    </>}
  </section>
}
