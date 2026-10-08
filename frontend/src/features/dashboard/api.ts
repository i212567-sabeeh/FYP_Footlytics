import { useQueries } from '@tanstack/react-query'
import { listRecords } from '../football/api'
import { jobsKey } from '../media/api'
import type { ProcessingJob } from '../media/types'

/**
 * The most relevant job for each match: the job API lists active jobs first,
 * then the newest, so one record per match suffices. Results are cached briefly
 * and never polled; callers enable this only for roles allowed to read jobs.
 */
export function useLatestJobs(matchIds: readonly number[], enabled: boolean) {
  return useQueries({
    queries: matchIds.map((id) => ({
      queryKey: [...jobsKey(id), 'latest'],
      queryFn: ({ signal }: { signal: AbortSignal }) => listRecords<ProcessingJob>(`matches/${id}/jobs`, { offset: 0, limit: 1 }, signal),
      enabled,
      staleTime: 30_000,
    })),
  })
}
