export interface Point { x: number; y: number }
export interface PointPair { image: Point; pitch: Point }

export interface CalibrationWrite {
  video_id: number
  source_timestamp_seconds: number
  image_points: Point[]
  pitch_points: Point[]
}

export interface PitchCalibration extends CalibrationWrite {
  id: number
  match_id: number
  source_frame_number: number
  image_width: number
  image_height: number
  pitch_length_metres: number
  pitch_width_metres: number
  homography_matrix: number[][]
  reprojection_error: number
  created_by_user_id: number
  created_at: string
  updated_at: string
}

export interface CalibrationFrameData {
  blob: Blob
  videoId: number
  frameNumber: number
  timestamp: number
  width: number
  height: number
}
