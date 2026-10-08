import { ApiError } from '../../api/client'
import type { PitchCalibration } from '../calibration/types'
import type { FootballMatch } from '../football/types'
import { isActiveJob, JOB_LABELS, type JobType, type MatchVideo, type ProcessingJob } from '../media/types'
import type { ReportStatus } from '../reports/api'

export type StageKey = 'video' | 'calibration' | JobType
export type StageState = 'checking' | 'not_started' | 'queued' | 'running' | 'completed' | 'completed_with_warnings'
  | 'failed' | 'cancelled' | 'stale' | 'unknown'
export type StagePage = 'video' | 'processing' | 'calibration' | 'review' | 'analytics'
export interface StageDefinition { key: StageKey; label: string; requires: readonly StageKey[]; startable: boolean; optional?: boolean; page?: StagePage }
export interface StageView { key: StageKey; state: StageState; detail?: string; job?: ProcessingJob }
/** The parts of a query result the resolvers read. */
export interface Probe<T> { data: T | undefined; error: Error | null }

// Mirrors the backend job guards (job_service._create_job): detection needs a
// current calibration, tracking current detections, mapping tracking and
// calibration, team tactics trajectories and team assignments. Preparation is
// independent; a report captures whichever saved results are available.
export const STAGES: readonly StageDefinition[] = [
  { key: 'video', label: 'Match video', requires: [], startable: false, page: 'video' },
  { key: 'video_preparation', label: JOB_LABELS.video_preparation, requires: ['video'], startable: false, optional: true, page: 'processing' },
  { key: 'calibration', label: 'Pitch calibration', requires: ['video'], startable: false, page: 'calibration' },
  { key: 'player_detection', label: JOB_LABELS.player_detection, requires: ['calibration'], startable: true, page: 'review' },
  { key: 'player_tracking', label: JOB_LABELS.player_tracking, requires: ['calibration', 'player_detection'], startable: true, page: 'review' },
  { key: 'team_classification', label: JOB_LABELS.team_classification, requires: ['player_tracking'], startable: true, page: 'analytics' },
  { key: 'coordinate_mapping', label: JOB_LABELS.coordinate_mapping, requires: ['calibration', 'player_tracking'], startable: true },
  { key: 'trajectory_cleaning', label: JOB_LABELS.trajectory_cleaning, requires: ['coordinate_mapping'], startable: true },
  { key: 'player_analytics', label: JOB_LABELS.player_analytics, requires: ['trajectory_cleaning'], startable: true, page: 'analytics' },
  { key: 'team_tactical_analytics', label: JOB_LABELS.team_tactical_analytics, requires: ['trajectory_cleaning', 'team_classification'], startable: true, page: 'analytics' },
  { key: 'match_report', label: JOB_LABELS.match_report, requires: ['video'], startable: true, optional: true, page: 'analytics' },
]
export const STAGE = Object.fromEntries(STAGES.map((stage) => [stage.key, stage])) as Record<StageKey, StageDefinition>
export const STAGE_GROUPS: readonly { label: string; stages: readonly StageKey[] }[] = [
  { label: 'Source', stages: ['video', 'video_preparation', 'calibration'] },
  { label: 'Detection & tracking', stages: ['player_detection', 'player_tracking'] },
  { label: 'Teams & pitch positions', stages: ['team_classification', 'coordinate_mapping', 'trajectory_cleaning'] },
  { label: 'Analytics & reports', stages: ['player_analytics', 'team_tactical_analytics', 'match_report'] },
]
/** Topological order for suggesting a next step; optional preparation is never suggested. */
const ACTION_ORDER: readonly StageKey[] = ['calibration', 'player_detection', 'player_tracking', 'coordinate_mapping',
  'trajectory_cleaning', 'player_analytics', 'team_classification', 'team_tactical_analytics', 'match_report']
export type ResultStage = 'player_detection' | 'player_tracking' | 'team_classification' | 'coordinate_mapping'
  | 'trajectory_cleaning' | 'player_analytics' | 'team_tactical_analytics'
export const RESULT_STAGES: readonly ResultStage[] = ['player_detection', 'player_tracking', 'team_classification',
  'coordinate_mapping', 'trajectory_cleaning', 'player_analytics', 'team_tactical_analytics']

// Same rule as ResultState and the analytics overview: these 404/409 messages mean regenerate.
const STALE = /stale|changed|replaced/i
export const isDone = (state: StageState) => state === 'completed' || state === 'completed_with_warnings'
const ended = (job: ProcessingJob | undefined) => job?.status === 'failed' || job?.status === 'cancelled'
const unavailable = (error: Error | null) => error instanceof ApiError && [404, 409].includes(error.status)
// Jobs arrive active first, then newest, so the first match is the latest attempt.
const latestOf = (jobs: readonly ProcessingJob[], type: JobType) => jobs.find((job) => job.job_type === type)
const latestSuccess = (jobs: readonly ProcessingJob[], type: JobType) =>
  jobs.find((job) => job.job_type === type && (job.status === 'completed' || job.status === 'completed_with_warnings'))

export function progressText(job: ProcessingJob): string {
  return `${job.progress_percent}% complete${job.current_stage ? ` · ${job.current_stage.replaceAll('_', ' ')}` : ''}`
}

function field(data: unknown, name: 'status' | 'video_id'): unknown {
  return typeof data === 'object' && data !== null && name in data ? (data as Record<string, unknown>)[name] : undefined
}

/**
 * A job stage is Completed only when the backend's current-result endpoint
 * confirms a result for the current video and inputs; an old successful job
 * alone never counts. Running work and failed latest attempts come from jobs.
 */
export function resolveJobStage(type: JobType, jobs: readonly ProcessingJob[], probe: Probe<unknown>, videoId: number): StageView {
  const latest = latestOf(jobs, type)
  if (latest && isActiveJob(latest)) return { key: type, state: latest.status, job: latest, detail: progressText(latest) }
  const resultVideo = field(probe.data, 'video_id')
  if (probe.data !== undefined && !probe.error && (resultVideo === undefined || resultVideo === videoId)) {
    // The latest successful job published the current result, so its warning explains it.
    const success = latestSuccess(jobs, type)
    const warned = field(probe.data, 'status') === 'completed_with_warnings' || success?.status === 'completed_with_warnings'
    return { key: type, state: warned ? 'completed_with_warnings' : 'completed', job: latest,
      detail: ended(latest) ? 'The latest attempt did not finish; the saved result is still current.' : warned ? success?.warning_message ?? undefined : undefined }
  }
  if (latest && ended(latest)) return { key: type, state: latest.status, job: latest, detail: latest.error_message ?? undefined }
  if (probe.error) {
    if (!unavailable(probe.error)) return { key: type, state: 'unknown', detail: probe.error.message }
    // A completed job whose result is no longer current must be regenerated.
    return STALE.test(probe.error.message) || latestSuccess(jobs, type)
      ? { key: type, state: 'stale', job: latest, detail: probe.error.message }
      : { key: type, state: 'not_started' }
  }
  if (probe.data !== undefined) return { key: type, state: 'stale', job: latest, detail: 'The saved result belongs to an earlier video.' }
  return { key: type, state: 'checking' }
}

export function resolveVideo(probe: Probe<MatchVideo | null>): StageView {
  if (probe.error) return { key: 'video', state: 'unknown', detail: probe.error.message }
  if (probe.data === undefined) return { key: 'video', state: 'checking' }
  return probe.data ? { key: 'video', state: 'completed' } : { key: 'video', state: 'not_started', detail: 'Upload a match video to begin.' }
}

export function resolvePreparation(probe: Probe<ProcessingJob | null>, videoId: number): StageView {
  if (probe.error) return { key: 'video_preparation', state: 'unknown', detail: probe.error.message }
  if (probe.data === undefined) return { key: 'video_preparation', state: 'checking' }
  const job = probe.data?.video_id === videoId ? probe.data : null
  if (!job) return { key: 'video_preparation', state: 'not_started', detail: 'Optional check of the current source video.' }
  return { key: 'video_preparation', state: job.status, job,
    detail: isActiveJob(job) ? progressText(job) : job.error_message ?? job.warning_message ?? undefined }
}

export function resolveCalibration(probe: Probe<PitchCalibration | null>, video: MatchVideo, match: FootballMatch): StageView {
  if (probe.error) return unavailable(probe.error) ? { key: 'calibration', state: 'not_started' } : { key: 'calibration', state: 'unknown', detail: probe.error.message }
  if (probe.data === undefined) return { key: 'calibration', state: 'checking' }
  const saved = probe.data
  if (!saved) return { key: 'calibration', state: 'not_started' }
  // The same currency check the review page applies before processing.
  if (saved.video_id !== video.id || saved.pitch_length_metres !== match.pitch_length_metres || saved.pitch_width_metres !== match.pitch_width_metres) {
    return { key: 'calibration', state: 'stale', detail: 'The saved calibration does not match the current video or pitch dimensions.' }
  }
  return { key: 'calibration', state: 'completed' }
}

export function resolveReport(jobs: readonly ProcessingJob[], probe: Probe<ReportStatus>): StageView {
  const latest = latestOf(jobs, 'match_report')
  if (latest && isActiveJob(latest)) return { key: 'match_report', state: latest.status, job: latest, detail: progressText(latest) }
  if (probe.error) return { key: 'match_report', state: 'unknown', detail: probe.error.message }
  if (!probe.data) return { key: 'match_report', state: 'checking' }
  if (probe.data.current) {
    const warning = latestSuccess(jobs, 'match_report')?.status === 'completed_with_warnings'
    return { key: 'match_report', state: warning ? 'completed_with_warnings' : 'completed', job: latest,
      detail: warning ? latestSuccess(jobs, 'match_report')?.warning_message ?? undefined : undefined }
  }
  if (latest && ended(latest)) return { key: 'match_report', state: latest.status, job: latest, detail: latest.error_message ?? undefined }
  if (probe.data.stale) return { key: 'match_report', state: 'stale', detail: 'Analytics changed after the saved report was generated.' }
  return { key: 'match_report', state: 'not_started' }
}

export interface PipelineEvidence {
  match: FootballMatch
  video: Probe<MatchVideo | null>
  jobs: readonly ProcessingJob[]
  preparation: Probe<ProcessingJob | null>
  calibration: Probe<PitchCalibration | null>
  results: Record<ResultStage, Probe<unknown>>
  report: Probe<ReportStatus>
}

/** Resolves every stage for the current video; nothing is inferred without a video. */
export function resolvePipeline(evidence: PipelineEvidence): Record<StageKey, StageView> {
  const video = resolveVideo(evidence.video)
  const current = evidence.video.data
  const views = { video } as Record<StageKey, StageView>
  for (const stage of STAGES.slice(1)) {
    views[stage.key] = { key: stage.key, state: video.state === 'not_started' ? 'not_started' : video.state === 'unknown' ? 'unknown' : 'checking' }
  }
  if (!current) return views
  const jobs = evidence.jobs.filter((job) => job.video_id === current.id)
  views.video_preparation = resolvePreparation(evidence.preparation, current.id)
  views.calibration = resolveCalibration(evidence.calibration, current, evidence.match)
  for (const stage of RESULT_STAGES) views[stage] = resolveJobStage(stage, jobs, evidence.results[stage], current.id)
  views.match_report = resolveReport(jobs, evidence.report)
  return views
}

export const requirementsMet = (key: StageKey, views: Record<StageKey, StageView>) =>
  STAGE[key].requires.every((dependency) => isDone(views[dependency].state))

export type NextAction =
  | { kind: 'upload' }
  | { kind: 'wait'; job: ProcessingJob }
  | { kind: 'calibrate'; stale: boolean }
  | { kind: 'run'; stage: JobType; stale: boolean }
  | { kind: 'retry'; stage: JobType; job: ProcessingJob }
  | { kind: 'done' }
  | { kind: 'unknown' }

/**
 * The first stage, in dependency order, that is not current and whose inputs
 * are. Unknown or still-loading evidence yields no recommendation, never a guess.
 */
export function nextAction(views: Record<StageKey, StageView>, activeJob: ProcessingJob | undefined): NextAction {
  if (views.video.state === 'not_started') return { kind: 'upload' }
  if (views.video.state !== 'completed') return { kind: 'unknown' }
  if (activeJob) return { kind: 'wait', job: activeJob }
  for (const key of ACTION_ORDER) {
    const view = views[key]
    if (isDone(view.state) || !requirementsMet(key, views)) continue
    if (key === 'calibration') return view.state === 'not_started' || view.state === 'stale' ? { kind: 'calibrate', stale: view.state === 'stale' } : { kind: 'unknown' }
    if ((view.state === 'failed' || view.state === 'cancelled') && view.job) return { kind: 'retry', stage: key as JobType, job: view.job }
    if (view.state === 'not_started' || view.state === 'stale') return { kind: 'run', stage: key as JobType, stale: view.state === 'stale' }
    return { kind: 'unknown' }
  }
  return { kind: 'done' }
}
