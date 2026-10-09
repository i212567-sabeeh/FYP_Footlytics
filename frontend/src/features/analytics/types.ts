// Public Phase 8/10/11/12 contracts. Track IDs are not roster-player identities.
export type TacticalTeam = 'team_a' | 'team_b'
export type TrackTeam = TacticalTeam | 'unknown'
export const TEAM_LABELS: Record<TrackTeam, string> = { team_a: 'Team A', team_b: 'Team B', unknown: 'Unknown' }

export interface TeamAssignment {
  match_id: number
  tracking_job_id: number
  track_id: number
  automatic_team: TrackTeam
  automatic_confidence: number
  classification_mode?: 'automatic' | 'user_seeded'
  classification_provenance?: { prototype_set_id: number | null; sample_ids: string[]; sample_count: number; margin: number | null; rejection_reason: string | null } | null
  manual_team: TrackTeam | null
  effective_team: TrackTeam
  updated_by_user_id: number | null
  created_at: string
  updated_at: string
}

export interface ObservationCoverage {
  video_duration_seconds: number | null
  observed_coverage_percent: number | null
  coverage_warning: string | null
}

export interface PlayerAnalytics extends ObservationCoverage {
  match_id: number
  video_id: number
  job_id: number
  trajectory_job_id: number
  track_id: number
  first_frame: number | null
  last_frame: number | null
  first_timestamp: number | null
  last_timestamp: number | null
  segment_count: number
  usable_observation_count: number
  valid_interval_count: number
  excluded_interval_count: number
  active_duration_seconds: number
  total_distance_metres: number
  average_speed_mps: number | null
  average_speed_kmh: number | null
  max_speed_mps: number | null
  max_speed_kmh: number | null
  sprint_count: number
  sprint_distance_metres: number
  sprint_duration_seconds: number
  /** Minimum duration of one movement measurement; 0 means every consecutive observation. */
  speed_window_seconds?: number
}

export interface HeatmapCell {
  track_id: number
  x_bin: number
  y_bin: number
  x_min: number
  x_max: number
  y_min: number
  y_max: number
  occupancy_seconds: number
  occupancy_fraction: number
}

export interface TrackHeatmap extends ObservationCoverage {
  match_id: number
  video_id: number
  job_id: number
  trajectory_job_id: number
  track_id: number
  pitch_length_metres: number
  pitch_width_metres: number
  bins_x: number
  bins_y: number
  method: 'interval_start_time_weighted'
  total_occupancy_seconds: number
  cells: HeatmapCell[]
}

export interface TeamTacticalSummary {
  team: TacticalTeam
  valid_snapshots: number
  insufficient_snapshots: number
  avg_visible_players: number | null
  avg_centroid_x: number | null
  avg_centroid_y: number | null
  avg_width_metres: number | null
  avg_depth_metres: number | null
  avg_compactness_radius_metres: number | null
  avg_pairwise_distance_metres: number | null
  hull_snapshots: number
  avg_convex_hull_area_m2: number | null
  avg_bounding_box_area_m2: number | null
  both_teams_valid_snapshots: number
  avg_centroid_distance_to_opponent_metres: number | null
}

export interface TeamSnapshot {
  frame_number: number
  timestamp_seconds: number
  team: TacticalTeam
  visible_players: number
  sufficient_players: boolean
  centroid_x: number | null
  centroid_y: number | null
  width_metres: number | null
  depth_metres: number | null
  compactness_radius_metres: number | null
  mean_pairwise_distance_metres: number | null
  convex_hull_area_m2: number | null
  bounding_box_area_m2: number | null
  centroid_distance_to_opponent_metres: number | null
}

export interface TeamAnalytics {
  match_id: number
  video_id: number
  job_id: number
  summary: {
    source_rows: number
    usable_rows: number
    rejected_rows: number
    assigned_rows: number
    unknown_rows: number
    observed_frames: number
    trajectory_job_id: number
    trajectory_attempt: number
    pitch_length_metres: number
    pitch_width_metres: number
    min_players_per_team: number
    aggregation: 'per_valid_snapshot'
    snapshot_method: 'usable_positions_by_frame'
    artifact_format: 'csv_bundle'
  }
  teams: TeamTacticalSummary[]
}

export interface TrajectoryResult {
  job_id: number
  job_updated_at: string
  status: 'completed' | 'completed_with_warnings'
  video_id: number
  source_rows: number
  usable_rows: number
  rejected_rows: number
  outside_pitch_rows: number
  jump_outlier_rows: number
  invalid_temporal_rows: number
  interpolated_rows: 0
  smoothed_rows: number
  unique_tracks: number
  segments: number
  first_frame: number | null
  last_frame: number | null
  coordinate_job_id: number
  coordinate_attempt: number
  pitch_length_metres: number
  pitch_width_metres: number
  max_plausible_speed_mps: number
  max_gap_seconds: number
  smoothing_window: number
  smoothing_max_shift_metres: number
  interpolation_policy: 'none_preserve_gaps'
  method: 'neighbor_filter_time_residual_median_v1'
  coordinate_unit: 'metres'
  artifact_format: 'csv'
}
