import type { JobStatus } from '../media/types'

export type ReviewKind = 'detections' | 'tracking'

interface ReviewBase {
  job_id: number
  job_updated_at: string
  status: JobStatus
  video_id: number
  processed_frames: number
  frame_stride: number
  first_frame: number
  last_frame: number
  frame_width: number
  frame_height: number
}

export interface DetectionReviewSummary extends ReviewBase {
  total_detections: number
  average_detections_per_processed_frame: number
}

export interface TrackingReviewSummary extends ReviewBase {
  unique_tracks: number
  tracked_rows: number
  average_visible_tracks_per_frame: number
}

export type ReviewSummary = DetectionReviewSummary | TrackingReviewSummary

export interface ReviewFrame {
  blob: Blob
  frameNumber: number
  timestamp: number
  width: number
  height: number
}
