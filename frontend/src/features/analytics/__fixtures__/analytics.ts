// Deterministic API fixtures for tests/browser review only; never imported by the app.
import type { User } from '../../auth/types'
import type { FootballMatch } from '../../football/types'
import type { MatchVideo, ProcessingJob } from '../../media/types'
import type { PlayerAnalytics, TeamAnalytics, TeamAssignment, TeamSnapshot, TrackHeatmap, TrajectoryResult } from '../types'

export const date = '2026-10-04T12:00:00Z'
export const user: User = { id: 1, email: 'analytics@example.com', full_name: 'Analytics Coach', roles: ['coach'], is_active: true, created_at: date, updated_at: date }
export const match: FootballMatch = {
  id: 1, club_id: 1, club: { id: 1, name: 'Fixture Club', is_active: true }, title: 'Analytics Test Match', team_a_id: 1, team_b_id: 2,
  team_a: { id: 1, club_id: 1, name: 'Fixture Blue', is_active: true }, team_b: { id: 2, club_id: 1, name: 'Fixture Amber', is_active: true },
  match_format: '5v5', match_date: date, pitch_length_metres: 40, pitch_width_metres: 20, venue: null, notes: null,
  is_archived: false, created_by_user_id: 1, created_by: { id: 1, full_name: user.full_name }, created_at: date, updated_at: date,
}
export const video: MatchVideo = { id: 2, match_id: 1, original_filename: 'fixture-match.mp4', file_size_bytes: 1024,
  width: 640, height: 360, fps: 30, duration_seconds: 300, frame_count: 9000, mime_type: 'video/mp4',
  codec: 'h264', container_format: 'mp4', uploaded_by_user_id: 1, sha256: null, warning_message: null, created_at: date, updated_at: date }
export const job: ProcessingJob = { id: 11, match_id: 1, video_id: 2, job_type: 'player_analytics', status: 'completed', progress_percent: 100,
  current_stage: 'completed', created_by_user_id: 1, started_at: date, finished_at: date, error_message: null, warning_message: null,
  retry_count: 0, created_at: date, updated_at: date }
export const player: PlayerAnalytics = {
  video_duration_seconds: 300, observed_coverage_percent: 21.6666666666667, coverage_warning: null,
  match_id: 1, video_id: 2, job_id: 11, trajectory_job_id: 10, track_id: 3, first_frame: 0, last_frame: 2400,
  first_timestamp: 0, last_timestamp: 80, segment_count: 2, usable_observation_count: 101, valid_interval_count: 99, excluded_interval_count: 1,
  active_duration_seconds: 65, total_distance_metres: 123.45, average_speed_mps: 123.45 / 65, average_speed_kmh: 123.45 / 65 * 3.6,
  max_speed_mps: 7.5, max_speed_kmh: 27, sprint_count: 2, sprint_distance_metres: 30.5, sprint_duration_seconds: 4.2,
}
export const players: PlayerAnalytics[] = [player, { ...player, track_id: 17, observed_coverage_percent: 0, coverage_warning: 'No usable observed intervals.', total_distance_metres: 0,
  segment_count: 1, usable_observation_count: 1, valid_interval_count: 0, excluded_interval_count: 0, last_frame: 0, last_timestamp: 0,
  average_speed_mps: null, average_speed_kmh: null, max_speed_mps: null, max_speed_kmh: null,
  active_duration_seconds: 0, sprint_count: 0, sprint_distance_metres: 0, sprint_duration_seconds: 0 }]
export const assignments: TeamAssignment[] = [
  { match_id: 1, tracking_job_id: 7, track_id: 3, automatic_team: 'team_a', automatic_confidence: 0.9,
    manual_team: null, effective_team: 'team_a', updated_by_user_id: null, created_at: date, updated_at: date },
  { match_id: 1, tracking_job_id: 7, track_id: 17, automatic_team: 'unknown', automatic_confidence: 0,
    manual_team: null, effective_team: 'unknown', updated_by_user_id: null, created_at: date, updated_at: date },
]
export const heatmap: TrackHeatmap = {
  video_duration_seconds: 300, observed_coverage_percent: 21.6666666666667, coverage_warning: null,
  match_id: 1, video_id: 2, job_id: 11, trajectory_job_id: 10, track_id: 3,
  pitch_length_metres: 40, pitch_width_metres: 20, bins_x: 4, bins_y: 4,
  method: 'interval_start_time_weighted', total_occupancy_seconds: 65,
  cells: [
    { track_id: 3, x_bin: 1, y_bin: 2, x_min: 10, x_max: 20, y_min: 10, y_max: 15, occupancy_seconds: 13, occupancy_fraction: 0.2 },
    { track_id: 3, x_bin: 3, y_bin: 0, x_min: 30, x_max: 40, y_min: 0, y_max: 5, occupancy_seconds: 52, occupancy_fraction: 0.8 },
  ],
}
export const tactics: TeamAnalytics = { match_id: 1, video_id: 2, job_id: 12,
  summary: { source_rows: 18, usable_rows: 16, rejected_rows: 2, assigned_rows: 14, unknown_rows: 2, observed_frames: 4,
    trajectory_job_id: 10, trajectory_attempt: 0, pitch_length_metres: 40, pitch_width_metres: 20, min_players_per_team: 2,
    aggregation: 'per_valid_snapshot', snapshot_method: 'usable_positions_by_frame', artifact_format: 'csv_bundle' },
  teams: [
    { team: 'team_a', valid_snapshots: 3, insufficient_snapshots: 1, avg_visible_players: 3, avg_centroid_x: 14.25, avg_centroid_y: 8.5,
      avg_width_metres: 9.2, avg_depth_metres: 16.8, avg_compactness_radius_metres: 6.4, avg_pairwise_distance_metres: 10.8,
      hull_snapshots: 2, avg_convex_hull_area_m2: 50.5, avg_bounding_box_area_m2: 154.56, both_teams_valid_snapshots: 3,
      avg_centroid_distance_to_opponent_metres: 9.5 },
    { team: 'team_b', valid_snapshots: 4, insufficient_snapshots: 0, avg_visible_players: 2.5, avg_centroid_x: 25.5, avg_centroid_y: 12.25,
      avg_width_metres: 5.6, avg_depth_metres: 11.2, avg_compactness_radius_metres: 4.3, avg_pairwise_distance_metres: 8.6,
      hull_snapshots: 0, avg_convex_hull_area_m2: null, avg_bounding_box_area_m2: 62.72, both_teams_valid_snapshots: 3,
      avg_centroid_distance_to_opponent_metres: 9.5 },
  ],
}
export const snapshot: TeamSnapshot = { frame_number: 0, timestamp_seconds: 0, team: 'team_a', visible_players: 3,
  sufficient_players: true, centroid_x: 14.25, centroid_y: 8.5, width_metres: 9.2, depth_metres: 16.8,
  compactness_radius_metres: 6.4, mean_pairwise_distance_metres: 10.8, convex_hull_area_m2: 50.5,
  bounding_box_area_m2: 154.56, centroid_distance_to_opponent_metres: 9.5 }
export const seriesA: TeamSnapshot[] = [snapshot,
  { frame_number: 30, timestamp_seconds: 1, team: 'team_a', visible_players: 1, sufficient_players: false,
    centroid_x: null, centroid_y: null, width_metres: null, depth_metres: null, compactness_radius_metres: null,
    mean_pairwise_distance_metres: null, convex_hull_area_m2: null, bounding_box_area_m2: null, centroid_distance_to_opponent_metres: null },
  { ...snapshot, frame_number: 60, timestamp_seconds: 2, width_metres: 12.8 },
  { ...snapshot, frame_number: 90, timestamp_seconds: 3, width_metres: 10.6 },
]
export const seriesB: TeamSnapshot[] = seriesA.map((row) => ({ ...snapshot, team: 'team_b', frame_number: row.frame_number,
  timestamp_seconds: row.timestamp_seconds, width_metres: 5.6, depth_metres: 11.2, centroid_x: 25.5, centroid_y: 12.25 }))
export const trajectories: TrajectoryResult = { job_id: 10, job_updated_at: date, status: 'completed', video_id: 2,
  source_rows: 18, usable_rows: 16, rejected_rows: 2, unique_tracks: 2, segments: 3, pitch_length_metres: 40, pitch_width_metres: 20,
  outside_pitch_rows: 1, jump_outlier_rows: 1, invalid_temporal_rows: 0, interpolated_rows: 0, smoothed_rows: 0,
  first_frame: 0, last_frame: 2400, coordinate_job_id: 9, coordinate_attempt: 0, max_plausible_speed_mps: 12,
  max_gap_seconds: 2, smoothing_window: 3, smoothing_max_shift_metres: 0.5,
  interpolation_policy: 'none_preserve_gaps', method: 'neighbor_filter_time_residual_median_v1', coordinate_unit: 'metres', artifact_format: 'csv' }
