import { useQuery } from '@tanstack/react-query'
import { ApiError, apiRequest } from '../../api/client'
import { listRecords } from '../football/api'
import { mediaKey } from '../media/api'
import type { JobType, ProcessingJob } from '../media/types'
import type { PlayerAnalytics, TeamAnalytics, TeamAssignment, TeamSnapshot, TrackHeatmap, TrajectoryResult } from './types'

export const analyticsKey = (matchId: number) => [...mediaKey(matchId), 'analytics'] as const
export const playerKey = (matchId: number) => [...analyticsKey(matchId), 'players'] as const
export const tacticsKey = (matchId: number) => [...analyticsKey(matchId), 'tactics'] as const
export const assignmentsKey = (matchId: number) => [...analyticsKey(matchId), 'assignments'] as const
export const trajectoryKey = (matchId: number) => [...analyticsKey(matchId), 'trajectories'] as const
export const SERIES_LIMIT = 100

export function jobVersion(jobs: ProcessingJob[], kinds: readonly JobType[]): string {
  return jobs.filter((job) => kinds.includes(job.job_type))
    .map((job) => `${job.id}:${job.status}:${job.retry_count}`).join('|')
}

export function usePlayerAnalytics(matchId: number, version: string, offset: number) {
  return useQuery({ queryKey: [...playerKey(matchId), version, 'list', offset], gcTime: 0,
    queryFn: ({ signal }) => listRecords<PlayerAnalytics>(`matches/${matchId}/player-analytics`, { offset, limit: 25 }, signal) })
}
export function usePlayerDetail(matchId: number, version: string, trackId: number | null) {
  return useQuery({ queryKey: [...playerKey(matchId), version, 'detail', trackId], gcTime: 0, enabled: trackId !== null,
    queryFn: ({ signal }) => apiRequest<PlayerAnalytics>(`matches/${matchId}/player-analytics/${trackId}`, { signal }) })
}
export function useHeatmap(matchId: number, version: string, trackId: number | null) {
  return useQuery({ queryKey: [...playerKey(matchId), version, 'heatmap', trackId], gcTime: 0, enabled: trackId !== null,
    queryFn: ({ signal }) => apiRequest<TrackHeatmap>(`matches/${matchId}/player-analytics/${trackId}/heatmap`, { signal }) })
}
export function useTeamAnalytics(matchId: number, version: string) {
  return useQuery({ queryKey: [...tacticsKey(matchId), version, 'summary'], gcTime: 0,
    queryFn: ({ signal }) => apiRequest<TeamAnalytics>(`matches/${matchId}/team-analytics`, { signal }) })
}
export function useTrajectoryResult(matchId: number, version: string) {
  return useQuery({ queryKey: [...trajectoryKey(matchId), version], gcTime: 0,
    queryFn: ({ signal }) => apiRequest<TrajectoryResult>(`matches/${matchId}/trajectories/summary`, { signal }) })
}
export function useAssignments(matchId: number, version: string) {
  return useQuery({ queryKey: [...assignmentsKey(matchId), version], gcTime: 0,
    // Assignment metadata is per track, not per frame. Traverse bounded pages so
    // tracks beyond page one are never incorrectly labelled Unknown in the table.
    queryFn: async ({ signal }) => {
      const items: TeamAssignment[] = []
      let offset = 0
      while (true) {
        const page = await listRecords<TeamAssignment>(`matches/${matchId}/team-assignments`, { offset, limit: 100 }, signal)
        items.push(...page.items)
        offset += page.items.length
        if (offset >= page.total) return items
        if (!page.items.length) throw new ApiError(409, 'Team assignments changed while loading. Refresh analytics.')
      }
    } })
}
export function useTeamSeries(matchId: number, version: string, jobId: number, offset: number) {
  return useQuery({ queryKey: [...tacticsKey(matchId), version, 'series', { teams: ['team_a', 'team_b'], jobId, offset, limit: SERIES_LIMIT }], gcTime: 0,
    queryFn: async ({ signal }) => {
      const [a, b] = await Promise.all(['team_a', 'team_b'].map((team) =>
        listRecords<TeamSnapshot>(`matches/${matchId}/team-analytics/${team}/series`, { offset, limit: SERIES_LIMIT }, signal)))
      // Series pages have no job ID. Recheck the existing summary contract after
      // loading to avoid comparing pages from different publications.
      const current = await apiRequest<TeamAnalytics>(`matches/${matchId}/team-analytics`, { signal })
      if (!a || !b || current.job_id !== jobId || a.total !== b.total) {
        throw new ApiError(409, 'Team tactics changed. Refresh analytics to load the current result.')
      }
      return { a, b }
    } })
}
