import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '../../api/client'
import { listRecords } from '../football/api'
import { isActiveJob, type MatchVideo, type ProcessingJob } from './types'

export const mediaKey = (matchId: number) => ['football', 'media', matchId] as const
export const videoKey = (matchId: number) => [...mediaKey(matchId), 'video'] as const
export const jobsKey = (matchId: number) => [...mediaKey(matchId), 'jobs'] as const

export function useMatchVideo(matchId: number) {
  return useQuery({
    queryKey: videoKey(matchId),
    queryFn: ({ signal }) => apiRequest<MatchVideo | null>(`matches/${matchId}/video`, { signal }),
  })
}

export function useMatchJobs(matchId: number, offset: number, enabled: boolean) {
  return useQuery({
    queryKey: [...jobsKey(matchId), offset],
    enabled,
    queryFn: ({ signal }) => listRecords<ProcessingJob>(`matches/${matchId}/jobs`, { offset, limit: 25 }, signal),
    // A failed refresh needs user attention. Terminal pages need no timer.
    refetchInterval: (query) => !query.state.error && query.state.data?.items.some(isActiveJob) ? 2000 : false,
  })
}

export function usePreparation(matchId: number, videoId: number | undefined, enabled: boolean) {
  return useQuery({
    queryKey: [...jobsKey(matchId), 'preparation', videoId],
    enabled,
    queryFn: ({ signal }) => apiRequest<ProcessingJob | null>(`matches/${matchId}/jobs/video-preparation`, { signal }),
    refetchInterval: (query) => !query.state.error && query.state.data && isActiveJob(query.state.data) ? 2000 : false,
  })
}

export function uploadVideo(matchId: number, file: File, replace: boolean) {
  const body = new FormData()
  body.append('file', file)
  return apiRequest<MatchVideo>(`matches/${matchId}/video`, { method: replace ? 'PUT' : 'POST', body })
}
