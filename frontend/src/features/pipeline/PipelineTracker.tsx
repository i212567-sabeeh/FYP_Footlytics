import type { ReactNode } from 'react'
import { useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { CircleCheck, CircleDashed, CircleQuestionMark, CircleSlash, CircleX, Clock3, LoaderCircle, Play, RefreshCw, RotateCw, TriangleAlert, Workflow, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router'
import { ApiError } from '../../api/client'
import type { FootballMatch, Page } from '../football/types'
import { mediaKey } from '../media/api'
import { isActiveJob, JOB_LABELS, JOB_STATUS_LABELS, type JobType, type MatchVideo, type ProcessingJob } from '../media/types'
import { usePipelineEvidence, useStageAction } from './api'
import { isDone, nextAction, progressText, requirementsMet, resolvePipeline, STAGE, STAGE_GROUPS, type NextAction, type StageDefinition, type StageKey, type StageState, type StageView } from './model'

const STATES: Record<StageState, [string, LucideIcon, string]> = {
  checking: ['Checking…', LoaderCircle, 'text-slate-400 ring-slate-600/50'],
  not_started: ['Not started', CircleDashed, 'text-slate-400 ring-slate-600/50'],
  queued: ['Queued', Clock3, 'text-slate-200 ring-slate-400/40'],
  running: ['Running', LoaderCircle, 'text-sky-300 ring-sky-400/40'],
  completed: ['Completed', CircleCheck, 'text-emerald-300 ring-emerald-400/40'],
  completed_with_warnings: ['Completed with warnings', TriangleAlert, 'text-amber-300 ring-amber-400/40'],
  failed: ['Failed', CircleX, 'text-red-300 ring-red-400/40'],
  cancelled: ['Cancelled', CircleSlash, 'text-slate-400 ring-slate-600/50'],
  stale: ['Needs regeneration', RefreshCw, 'text-amber-300 ring-amber-400/40'],
  unknown: ['Status unavailable', CircleQuestionMark, 'text-slate-400 ring-slate-600/50'],
}
type Run = (request: { stage: JobType; retryId?: number }) => void
const READ_ONLY = 'Read-only: an Admin, Coach or Analyst can do this on an editable match.'

function StageIcon({ state }: { state: StageState }) {
  const [, Icon, tone] = STATES[state]
  const spin = state === 'checking' || state === 'running' ? ' animate-spin motion-reduce:animate-none' : ''
  return <span aria-hidden="true" className={`relative grid size-8 shrink-0 place-items-center rounded-full bg-canvas ring-1 ${tone}`}><Icon className={`size-4${spin}`} /></span>
}

/** Stage status, read as "Status: …". The short visible label is CSS-generated,
 * so it is never confused with the job-history status text on the same page. */
function StageBadge({ state }: { state: StageState }) {
  const [label, , tone] = STATES[state]
  return <span className={`inline-flex shrink-0 rounded-full bg-canvas/60 px-2.5 py-0.5 text-xs font-medium ring-1 ${tone}`}>
    <span aria-hidden="true" data-label={label} className="before:content-[attr(data-label)]" />
    <span className="sr-only">{`Status: ${label}`}</span>
  </span>
}

function StageLink({ stage, matchId }: { stage: StageDefinition; matchId: number }) {
  const className = 'button-secondary min-h-8 px-3 py-1 text-xs'
  const label = `Open ${stage.label}`
  if (stage.page === 'video' || stage.page === 'processing') return <a href={`#${stage.page}-heading`} aria-label={label} className={className}>Open</a>
  return stage.page ? <Link to={`/matches/${matchId}/${stage.page}`} aria-label={label} className={className}>Open</Link> : null
}

function StageItem({ stage, view, views, matchId, canManage, busy, run, last }: {
  stage: StageDefinition; view: StageView; views: Record<StageKey, StageView>; matchId: number; canManage: boolean; busy: boolean; run: Run; last: boolean
}) {
  const ready = requirementsMet(stage.key, views)
  const runnable = canManage && stage.startable && ready && (view.state === 'not_started' || view.state === 'stale')
  const retryJob = canManage && stage.startable && ready && (view.state === 'failed' || view.state === 'cancelled') ? view.job : undefined
  return <li className="relative flex gap-3 pb-5 last:pb-0">
    {!last && <span aria-hidden="true" className="absolute bottom-0 left-4 top-9 w-px bg-line" />}
    <StageIcon state={view.state} />
    <div className="min-w-0 flex-1">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
        <p className="text-sm font-medium text-slate-100">{stage.label}{stage.optional && <span className="ml-2 text-xs font-normal text-slate-500">Optional</span>}</p>
        <StageBadge state={view.state} />
      </div>
      {view.detail && <p className="mt-1 break-words text-xs leading-5 text-slate-400">{view.detail}</p>}
      {!ready && !isDone(view.state) && stage.requires.length > 0 && <p className="mt-1 text-xs text-slate-500">
        Needs current {stage.requires.map((key) => STAGE[key].label.toLowerCase()).join(' and ')}</p>}
      <div className="mt-2 flex flex-wrap gap-2 empty:hidden">
        {runnable && <button type="button" className="button-secondary min-h-8 px-3 py-1 text-xs" disabled={busy}
          aria-label={`${view.state === 'stale' ? 'Regenerate' : 'Run'} ${stage.label}`} onClick={() => run({ stage: stage.key as JobType })}>
          <Play aria-hidden="true" className="size-3.5" />{view.state === 'stale' ? 'Regenerate' : 'Run'}</button>}
        {retryJob && <button type="button" className="button-secondary min-h-8 px-3 py-1 text-xs" disabled={busy}
          aria-label={`Retry ${stage.label}`} onClick={() => run({ stage: stage.key as JobType, retryId: retryJob.id })}>
          <RotateCw aria-hidden="true" className="size-3.5" />Retry</button>}
        <StageLink stage={stage} matchId={matchId} />
      </div>
    </div>
  </li>
}

function NextStep({ next, views, matchId, canManage, busy, run }: {
  next: NextAction; views: Record<StageKey, StageView>; matchId: number; canManage: boolean; busy: boolean; run: Run
}) {
  let title: string, body: string, action: ReactNode = null, actionable = true
  switch (next.kind) {
    case 'upload':
      title = 'Upload the match video'; body = 'Every processing stage starts from the current source video.'
      action = <a href="#video-heading" className="button-primary">Go to video upload</a>
      break
    case 'wait':
      title = `${JOB_LABELS[next.job.job_type]} is ${JOB_STATUS_LABELS[next.job.status].toLowerCase()}`
      body = `${progressText(next.job)}. One processing job runs at a time for each match.`; actionable = false
      break
    case 'calibrate':
      title = next.stale ? 'Recalibrate the pitch' : 'Calibrate the pitch'
      body = 'Player detection and pitch coordinates need a current calibration for this video.'
      action = <Link to={`/matches/${matchId}/calibration`} className="button-primary">Open calibration</Link>
      break
    case 'run': {
      const label = STAGE[next.stage].label
      title = `${next.stale ? 'Regenerate' : 'Run'} ${label.toLowerCase()}`
      body = next.stale ? views[next.stage].detail ?? 'Its saved result is no longer current.' : 'Its required inputs are current.'
      action = <button type="button" className="button-primary" disabled={busy} onClick={() => run({ stage: next.stage })}><Play aria-hidden="true" className="size-4" />Start {label}</button>
      break
    }
    case 'retry': {
      const label = STAGE[next.stage].label
      title = `Retry ${label.toLowerCase()}`; body = next.job.error_message ?? 'The latest attempt did not finish.'
      action = <button type="button" className="button-primary" disabled={busy} aria-label={`Retry ${label} now`}
        onClick={() => run({ stage: next.stage, retryId: next.job.id })}><RotateCw aria-hidden="true" className="size-4" />Retry now</button>
      break
    }
    case 'done':
      title = 'All stages are current'; body = 'Saved results match this video and its current inputs.'; actionable = false
      break
    default:
      title = Object.values(views).some((view) => view.state === 'checking') ? 'Checking current results' : 'No safe next step yet'
      body = 'A recommendation appears only when every required status is confirmed. Use the stage actions below.'; actionable = false
  }
  return <div className={`mt-5 flex flex-col gap-4 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between ${actionable
    ? 'border-emerald-400/30 bg-emerald-400/5' : 'border-line bg-canvas/40'}`}>
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-400">Next step</p>
      <p className="mt-1 font-semibold text-slate-50">{title}</p>
      <p className="mt-1 break-words text-sm text-slate-400">{body}</p>
      {actionable && !canManage && <p className="mt-2 text-xs text-slate-500">{READ_ONLY}</p>}
    </div>
    {canManage && action && <div className="shrink-0">{action}</div>}
  </div>
}

/**
 * Match processing overview built only from evidence: the current video, its
 * jobs and the backend's current-result checks. Visiting never starts a job.
 */
export function PipelineTracker({ match, video, jobs, preparation, canManage }: {
  match: FootballMatch; video: UseQueryResult<MatchVideo | null>; jobs: UseQueryResult<Page<ProcessingJob>>
  preparation: UseQueryResult<ProcessingJob | null>; canManage: boolean
}) {
  const client = useQueryClient()
  const items = jobs.data?.items ?? []
  const evidence = usePipelineEvidence(match, video.data, items, jobs.isSuccess)
  const views = resolvePipeline({ match, jobs: items, ...evidence,
    video: { data: video.data, error: video.error }, preparation: { data: preparation.data, error: preparation.error } })
  const activeJob = items.find(isActiveJob)
  const next: NextAction = jobs.isSuccess ? nextAction(views, activeJob) : { kind: 'unknown' }
  const action = useStageAction(match.id)
  const busy = Boolean(activeJob) || action.isPending
  const run: Run = (request) => { if (!busy) action.mutate(request) }
  const error = action.error instanceof ApiError && action.error.status === 503
    ? 'The processing queue is unavailable. Try again after the queue service is restored.' : action.error?.message

  return <section className="panel mt-8 min-w-0" aria-labelledby="pipeline-heading">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h2 id="pipeline-heading" className="flex items-center gap-2 text-xl font-semibold"><Workflow aria-hidden="true" className="size-5 text-emerald-300" />Processing pipeline</h2>
        <p className="mt-1 text-sm text-slate-400">Status comes from the current video&apos;s jobs and saved results. Opening this page never starts processing.</p>
      </div>
      <button type="button" className="button-secondary" onClick={() => void client.invalidateQueries({ queryKey: mediaKey(match.id) })}>
        <RefreshCw aria-hidden="true" className="size-4" />Refresh pipeline</button>
    </div>
    {jobs.error && <p className="mt-4 text-sm text-slate-400">Job status could not be loaded, so stage states are unavailable.</p>}
    <NextStep next={next} views={views} matchId={match.id} canManage={canManage} busy={busy} run={run} />
    {error && <p role="alert" className="mt-3 break-words text-sm text-red-300">{error}</p>}
    <div className="mt-6 grid gap-4 lg:grid-cols-2">
      {STAGE_GROUPS.map((group) => <div key={group.label} className="rounded-xl border border-line bg-canvas/40 p-4">
        <h3 className="mb-4 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{group.label}</h3>
        <ol className="list-none">
          {group.stages.map((key, index) => <StageItem key={key} stage={STAGE[key]} view={views[key]} views={views} matchId={match.id}
            canManage={canManage} busy={busy} run={run} last={index === group.stages.length - 1} />)}
        </ol>
      </div>)}
    </div>
  </section>
}
