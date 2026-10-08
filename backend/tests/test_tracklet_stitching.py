from dataclasses import replace

from app.evaluation.tracklet_stitching import (
    Observation,
    StitchPolicy,
    Tracklet,
    stitch_tracklets,
)


def track(tid, start, x=0, y=0, size=(20.0, 40.0), color=(50.0, 10.0, -25.0)):
    return Tracklet(
        tid,
        tuple(Observation(start + i * 0.1, (x + i * 0.1, y), size) for i in range(3)),
        color,
    )


def reasons(tracks, policy=None):
    mapping, decisions = stitch_tracklets(tracks, policy)
    return mapping, {d.reason for d in decisions}


def test_safe_short_continuation_preserves_provenance():
    mapping, decisions = stitch_tracklets([track(1, 0), track(2, 0.4, x=0.4)])
    assert mapping == {1: 1, 2: 1}
    accepted = [d for d in decisions if d.accepted]
    assert len(accepted) == 1
    assert accepted[0].source_tracklet == 1 and accepted[0].destination_tracklet == 2
    assert accepted[0].gap_seconds == 0.2


def test_overlapping_players_are_never_merged():
    mapping, why = reasons([track(1, 0), track(2, 0.1, x=0.3)])
    assert mapping == {1: 1, 2: 2} and "temporal_overlap" in why


def test_impossible_speed_rejected():
    assert "impossible_speed" in reasons([track(1, 0), track(2, 0.4, x=20)])[1]


def test_excessive_gap_rejected():
    assert "excessive_gap" in reasons([track(1, 0), track(2, 2, x=2)])[1]


def test_scale_mismatch_rejected():
    assert (
        "scale_mismatch"
        in reasons([track(1, 0), track(2, 0.4, x=0.4, size=(50.0, 100.0))])[1]
    )


def test_appearance_missing_or_different_never_uses_nearest_only():
    assert (
        "insufficient_appearance_evidence"
        in reasons([track(1, 0, color=None), track(2, 0.4, x=0.4)])[1]
    )
    assert (
        "appearance_mismatch"
        in reasons([track(1, 0), track(2, 0.4, x=0.4, color=(90.0, -30.0, 40.0))])[1]
    )


def test_two_nearby_crossing_players_are_rejected():
    mapping, why = reasons(
        [track(1, 0), track(2, 0.4, x=0.4), track(3, 0.2, x=0.2, y=0.5)]
    )
    assert len(set(mapping.values())) == 3
    assert "nearby_player_or_crossing" in why


def test_ambiguous_continuations_are_rejected_even_without_boundary_competitor():
    policy = replace(StitchPolicy(), competitor_distance_metres=0.0)
    mapping, why = reasons(
        [track(1, 0), track(2, 0.4, x=0.4), track(3, 0.4, x=0.41)], policy
    )
    assert len(set(mapping.values())) == 3
    assert "ambiguous_candidates" in why
