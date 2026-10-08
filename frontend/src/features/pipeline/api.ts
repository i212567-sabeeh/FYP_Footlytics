import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import { jobVersion } from '../analytics/api'
import { useCalibration } from '../calibration/api'
import type { FootballMatch } from '../football/types'
import { mediaKey } from '../media/api'
import type { JobType, MatchVideo, ProcessingJob } from '../media/types'
import type { ReportStatus } from '../reports/api'
import { useReviewSummary } from '../review/api'
import { RESULT_STAGES, type PipelineEvidence, type ResultStage } from './model'

export const pipelineKey = (matchId: number) => [...mediaKey(matchId), 'pipeline'] as const

// Current-result endpoints validate video, input versions and artifacts on the
// server. Paginated results need only one record to prove availability.
const RESULT_PATHS: Record<Exclude<ResultStage, 'player_detection' | 'player_tracking'>, string> = {
  team_classification: 'team-assignments?offset=0&limit=1',
  coordinate_mapping: 'coordinates/summary',
  trajectory_cleaning: 'trajectories/summary',
  player_analytics: 'player-analytics?offset=0&limit=1',
  team_tactical_analytics: 'team-analytics',
}
const ALL_JOBS: readonly JobType[] = ['video_preparation', ...RESULT_STAGES, 'match_report']

/**
 * Read-only evidence for the pipeline: one small request per stage for the
 * current video, refreshed when a current-video job changes state (not polled).
 */
export function usePipelineEvidence(match: FootballMatch, video: MatchVideo | null | undefined, jobs: readonly ProcessingJob[], enabled: boolean) {
  const current = jobs.filter((job) => job.video_id === video?.id)
  const version = `${video?.id}:${video?.updated_at}:${match.updated_at}:${jobVersion([...current], ALL_JOBS)}`
  const ready = enabled && Boolean(video)
  const calibration = useCalibration(match.id, ready ? video?.id : undefined)
  const detections = useReviewSummary(match.id, 'detections', video?.id, version, ready)
  const tracking = useReviewSummary(match.id, 'tracking', video?.id, version, ready)
  const stages = Object.keys(RESULT_PATHS) as (keyof typeof RESULT_PATHS)[]
  const results = useQueries({
    queries: stages.map((stage) => ({
      queryKey: [...pipelineKey(match.id), stage, version],
      queryFn: ({ signal }: { signal: AbortSignal }) => apiRequest<unknown>(`matches/${match.id}/${RESULT_PATHS[stage]}`, { signal }),
      enabled: ready, gcTime: 0, refetchOnWindowFocus: false,
    })),
  })
  const report = useQuery({
    queryKey: [...pipelineKey(match.id), 'report', version],
    queryFn: ({ signal }) => apiRequest<ReportStatus>(`matches/${match.id}/report`, { signal }),
    enabled: ready, gcTime: 0, refetchOnWindowFocus: false,
  })
  const probe = <T,>(query: { data: T | undefined; error: Error | null }) => ({ data: query.data, error: query.error })
  return {
    calibration: probe(calibration),
    report: probe(report),
    results: {
      player_detection: probe(detections), player_tracking: probe(tracking),
      ...Object.fromEntries(stages.map((stage, index) => [stage, probe(results[index]!)])),
    } as PipelineEvidence['results'],
  }
}

/** Starts or retries a job through the existing endpoints; the backend still
 * enforces permissions, prerequisites and the one-active-job rule. */
export function useStageAction(matchId: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ stage, retryId }: { stage: JobType; retryId?: number }) => apiRequest<ProcessingJob>(retryId === undefined
      ? `matches/${matchId}/jobs/${stage.replaceAll('_', '-')}` : `jobs/${retryId}/retry`, { method: 'POST' }),
    onSettled: () => client.invalidateQueries({ queryKey: mediaKey(matchId) }),
  })
}
