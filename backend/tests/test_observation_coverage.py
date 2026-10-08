"""Coverage describes existing cleaned intervals; it never changes heatmap bins."""

import pytest

from app.services.player_analytics_service import observation_coverage


@pytest.mark.parametrize(
    "observed, duration, percent, warning",
    [
        (72.4, 90, 80.4444444444, None),
        (12, 300, 4, "Short track fragment"),
        (30, 300, 10, "Low coverage"),
        (0, 300, 0, "No usable"),
        (0, None, None, "No usable"),
        (20, None, None, "unavailable"),
        (20, 0, None, "unavailable"),
        (20, float("nan"), None, "unavailable"),
        (20, 10, None, "inconsistent"),
    ],
)
def test_coverage_uses_real_duration_and_does_not_hide_missing_data(
    observed, duration, percent, warning
):
    data = observation_coverage(observed, duration)
    if percent is None:
        assert data["observed_coverage_percent"] is None
    else:
        assert data["observed_coverage_percent"] == pytest.approx(percent)
    if warning is None:
        assert data["coverage_warning"] is None
    else:
        assert warning in data["coverage_warning"]
