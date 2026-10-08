import type { JobStatus, ProcessingJob } from '../media/types'

/** Dashboard processing categories: genuine job states, with queued and running
 * grouped as active, plus matches that have no processing job yet. */
export type ProcessingState = 'active' | Exclude<JobStatus, 'queued' | 'running'> | 'none'

export const PROCESSING_ORDER: readonly ProcessingState[] = ['active', 'failed', 'completed_with_warnings', 'completed', 'cancelled', 'none']

export function processingState(job: ProcessingJob | undefined): ProcessingState {
  if (!job) return 'none'
  switch (job.status) {
    case 'queued':
    case 'running':
      return 'active'
    default:
      return job.status
  }
}

export function countStates(jobs: readonly (ProcessingJob | undefined)[]): Record<ProcessingState, number> {
  const counts = { active: 0, failed: 0, completed_with_warnings: 0, completed: 0, cancelled: 0, none: 0 }
  for (const job of jobs) counts[processingState(job)] += 1
  return counts
}
