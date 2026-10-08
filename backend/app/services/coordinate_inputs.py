"""Exact current tracking/calibration inputs, independent of team assignments."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.football import Match
from app.services.detection_inputs import current_calibration, snapshot
from app.services.result_inputs import ResultSource, current_result


@dataclass(frozen=True)
class CoordinateInputs:
    source: ResultSource
    calibration: dict


def current_mapping_inputs(
    session: Session, match: Match, settings: Settings
) -> CoordinateInputs:
    source = current_result(session, match, "tracking", settings)
    calibration = current_calibration(session, match, source.video)
    return CoordinateInputs(
        source,
        {
            **snapshot(calibration),
            # Retain the actual saved matrix as well as its ID/revision. No fitting.
            "homography_matrix": calibration.homography_matrix,
        },
    )
