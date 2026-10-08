export interface MatchVideo {
  id: number
  match_id: number
  original_filename: string
  file_size_bytes: number
  mime_type: string
  container_format: string | null
  codec: string | null
  width: number
  height: number
  fps: number
  duration_seconds: number
  frame_count: number | null
  uploaded_by_user_id: number
  sha256: string | null
  warning_message: string | null
  created_at: string
  updated_at: string
}

export type JobStatus = 'queued' | 'running' | 'completed' | 'completed_with_warnings' | 'failed' | 'cancelled'
export type JobType = 'video_preparation' | 'player_detection' | 'player_tracking'
  | 'team_classification' | 'coordinate_mapping' | 'trajectory_cleaning'
  | 'player_analytics' | 'team_tactical_analytics' | 'match_report'

export const JOB_LABELS: Record<JobType, string> = {
  video_preparation: 'Video preparation', player_detection: 'Player detection', player_tracking: 'Player tracking',
  team_classification: 'Team classification', coordinate_mapping: 'Pitch coordinate mapping',
  trajectory_cleaning: 'Trajectory cleaning', player_analytics: 'Player analytics',
  team_tactical_analytics: 'Team tactical analytics',
  match_report: 'Match PDF report',
}
export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  queued: 'Queued', running: 'Running', completed: 'Completed',
  completed_with_warnings: 'Completed with warnings', failed: 'Failed', cancelled: 'Cancelled',
}

export interface ProcessingJob {
  id: number
  match_id: number
  video_id: number
  job_type: JobType
  status: JobStatus
  progress_percent: number
  current_stage: string | null
  created_by_user_id: number
  started_at: string | null
  finished_at: string | null
  error_message: string | null
  warning_message: string | null
  retry_count: number
  created_at: string
  updated_at: string
}

export function isActiveJob(job: ProcessingJob): boolean {
  return job.status === 'queued' || job.status === 'running'
}
