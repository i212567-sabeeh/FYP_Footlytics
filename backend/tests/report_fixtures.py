"""Explicit synthetic saved Phase 11/12 outputs; never production fallback data."""

from app.database.base import utc_now
from app.models.football import Match
from app.models.media import ProcessingJob
from app.schemas.player_analytics import (
    AnalyticsSummary,
    HeatmapCell,
    MovementInterval,
    SprintEvent,
    TrackAnalytics,
)
from app.schemas.team_analytics import TacticsSummary, TeamTacticalSummary
from app.services.analytics_artifacts import AnalyticsArtifacts
from app.services.tactics_artifacts import TacticsArtifacts
from app.services.tactics_inputs import current_tactics_inputs


def player(track=1, empty=False):
    return TrackAnalytics(
        track_id=track,
        first_frame=0,
        last_frame=1 if empty else 3,
        first_timestamp=0,
        last_timestamp=0.1 if empty else 0.3,
        segment_count=1 if empty else 2,
        usable_observation_count=1 if empty else 3,
        valid_interval_count=0 if empty else 1,
        excluded_interval_count=0,
        active_duration_seconds=0 if empty else 0.1,
        total_distance_metres=0 if empty else 1,
        average_speed_mps=None if empty else 10,
        average_speed_kmh=None if empty else 36,
        max_speed_mps=None if empty else 10,
        max_speed_kmh=None if empty else 36,
        sprint_count=0 if empty else 1,
        sprint_distance_metres=0 if empty else 1,
        sprint_duration_seconds=0 if empty else 0.1,
    )


def team(label="team_a", empty=False):
    return TeamTacticalSummary(
        team=label,
        valid_snapshots=0 if empty else 2 if label == "team_a" else 3,
        insufficient_snapshots=3 if empty else 1 if label == "team_a" else 0,
        avg_visible_players=None if empty else 3,
        avg_centroid_x=None if empty else 23 / 6 if label == "team_a" else 41 / 3,
        avg_centroid_y=None if empty else 3 if label == "team_a" else 34 / 3,
        avg_width_metres=None if empty else 3,
        avg_depth_metres=None if empty else 4,
        avg_compactness_radius_metres=None if empty else 2.306790305337841,
        avg_pairwise_distance_metres=None if empty else 4,
        hull_snapshots=0 if empty else 2 if label == "team_a" else 3,
        avg_convex_hull_area_m2=None if empty else 6,
        avg_bounding_box_area_m2=None if empty else 12,
        both_teams_valid_snapshots=0,
        avg_centroid_distance_to_opponent_metres=None,
    )


def saved_analytics(session, settings, trajectories):
    # Hash persisted SQL numeric types just as the production request does.
    session.expire_all()
    inputs = current_tactics_inputs(
        session, session.get(Match, trajectories.match_id), settings
    )
    source = inputs.trajectories.summary
    jobs = []
    for kind in ("player_analytics", "team_tactical_analytics"):
        job = ProcessingJob(
            match_id=trajectories.match_id,
            video_id=trajectories.video_id,
            job_type=kind,
            status="completed",
            progress_percent=100,
            current_stage="completed",
            created_by_user_id=trajectories.created_by_user_id,
            attempt=0,
            retry_count=0,
            finished_at=utc_now(),
            trajectory_snapshot=inputs.trajectories.version,
            assignment_snapshot=inputs.assignment_version
            if kind == "team_tactical_analytics"
            else None,
        )
        session.add(job)
        session.flush()
        common = dict(
            source_rows=source.source_rows,
            usable_rows=source.usable_rows,
            rejected_rows=source.rejected_rows,
            trajectory_job_id=trajectories.id,
            trajectory_attempt=trajectories.attempt,
            pitch_length_metres=30,
            pitch_width_metres=20,
        )
        if kind == "player_analytics":
            summary = AnalyticsSummary(
                **common,
                unique_tracks=7,
                valid_intervals=7,
                excluded_intervals=0,
                sprint_events=7,
                heatmap_cells=7,
                sprint_speed_threshold_mps=7,
                sprint_min_duration_seconds=0.1,
                max_plausible_speed_mps=source.max_plausible_speed_mps,
                max_gap_seconds=source.max_gap_seconds,
                heatmap_bins_x=3,
                heatmap_bins_y=2,
            )
            with AnalyticsArtifacts(
                settings, job.match_id, job.video_id, job.id, 0
            ) as artifact:
                for track, (x, y) in zip(
                    (1, 2, 3, 4, 5, 6, 9),
                    ((2, 2), (6, 2), (2, 5), (12, 10), (16, 10), (12, 13), (20, 18)),
                    strict=True,
                ):
                    row = player(track)
                    if track == 3:
                        row = row.model_copy(
                            update=dict(
                                last_frame=1,
                                last_timestamp=0.1,
                                segment_count=1,
                                usable_observation_count=2,
                            )
                        )
                    artifact.write("players", row)
                    artifact.write(
                        "intervals",
                        MovementInterval(
                            track_id=track,
                            segment_id=1,
                            start_frame=0,
                            end_frame=1,
                            start_timestamp=0,
                            end_timestamp=0.1,
                            start_x=x,
                            start_y=y,
                            end_x=x + (track <= 3),
                            end_y=y + (track > 3),
                            dt_seconds=0.1,
                            distance_metres=1,
                            speed_mps=10,
                            speed_kmh=36,
                            above_sprint_threshold=True,
                        ),
                    )
                    artifact.write(
                        "sprints",
                        SprintEvent(
                            track_id=track,
                            segment_id=1,
                            start_frame=0,
                            end_frame=1,
                            start_timestamp=0,
                            end_timestamp=0.1,
                            duration_seconds=0.1,
                            distance_metres=1,
                            max_speed_mps=10,
                        ),
                    )
                    artifact.write(
                        "heatmaps",
                        HeatmapCell(
                            track_id=track,
                            x_bin=x // 10,
                            y_bin=y // 10,
                            x_min=x // 10 * 10,
                            x_max=(x // 10 + 1) * 10,
                            y_min=y // 10 * 10,
                            y_max=(y // 10 + 1) * 10,
                            occupancy_seconds=0.1,
                            occupancy_fraction=1,
                        ),
                    )
                job.artifact_relative_path = artifact.publish()
                job.analytics_summary = {
                    **summary.model_dump(mode="json"),
                    "artifact_versions": artifact.versions(),
                }
                session.commit()
                artifact.keep()
        else:
            summary = TacticsSummary(
                **common,
                assigned_rows=17,
                unknown_rows=3,
                observed_frames=3,
                min_players_per_team=3,
            )
            with TacticsArtifacts(
                settings, job.match_id, job.video_id, job.id, 0
            ) as artifact:
                for label in ("team_a", "team_b"):
                    artifact.write("team_tactics_summary", team(label))
                job.artifact_relative_path = artifact.publish()
                job.tactics_summary = {
                    **summary.model_dump(mode="json"),
                    "artifact_versions": artifact.versions(),
                }
                session.commit()
                artifact.keep()
        jobs.append(job)
    return jobs
