"""Pass-option geometry: lane defenders, target pressure and the offside line."""

import pytest

from matchmind.models.pass_options import pass_features, spadl_xy, xt_value


def test_lane_and_target_defenders() -> None:
    row = pass_features((80, 34), (100, 34), [(90, 35), (90, 36.5), (101, 34)], False)
    assert row["distance"] == pytest.approx(20)
    assert row["lane_opponents_1"] == 1
    assert row["lane_opponents_3"] == 2
    assert row["nearest_opponent_end"] == pytest.approx(1)
    assert row["opponents_near_end"] == 1


def test_offside_line_uses_second_last_defender() -> None:
    # Keeper at 104, last outfielder at 95: a target at 98 is beyond the line.
    row = pass_features((85, 30), (98, 40), [(104, 34), (95, 30), (90, 20)], True)
    assert row["beyond_offside_line"] == pytest.approx(3)
    assert row["under_pressure"] == 1


def test_coordinates_and_xt_orientation() -> None:
    assert spadl_xy([120, 0]) == (105, 68)
    # Central zone in front of goal is worth more than the far corner flag.
    assert xt_value(100, 34) > xt_value(100, 2) > xt_value(10, 34)
