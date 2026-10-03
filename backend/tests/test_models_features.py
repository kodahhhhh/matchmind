import numpy as np
import pytest

from matchmind.models.common import fold_map
from matchmind.models.xg import shot_features


def test_visible_goal_angle_and_freeze_frame_geometry() -> None:
    event = {
        "minute": 12,
        "location": [108, 40],
        "shot": {
            "body_part": {"name": "Right Foot"},
            "type": {"name": "Open Play"},
            "freeze_frame": [
                {
                    "location": [114, 40],
                    "teammate": False,
                    "position": {"name": "Goalkeeper"},
                },
                {
                    "location": [112, 40],
                    "teammate": False,
                    "position": {"name": "Center Back"},
                },
                {
                    "location": [112, 5],
                    "teammate": False,
                    "position": {"name": "Center Back"},
                },
            ],
        },
    }
    row = shot_features(event, {"pass": {"through_ball": True, "cross": True}})
    assert row["distance"] == pytest.approx(10.5)
    assert row["angle"] == pytest.approx(2 * np.arctan(3.66 / 10.5))
    assert row["opponents_in_cone"] == 2
    assert row["keeper_goal_distance"] == pytest.approx(5.25)
    assert row["keeper_shot_line_distance"] == 0
    assert row["through_ball"] == row["cross"] == 1
    event["shot"]["outcome"] = {"name": "Goal"}
    event["shot"]["end_location"] = [120, 40, 1]
    assert shot_features(event)["distance"] == row["distance"]
    assert "outcome" not in row


def test_missing_frame_is_distinct_from_empty_cone() -> None:
    row = shot_features({"minute": 0, "location": [100, 40], "shot": {}})
    assert row["freeze_frame_present"] == 0
    assert np.isnan(row["keeper_goal_distance"])


def test_match_split_is_complete_and_reproducible() -> None:
    splits = fold_map()
    assert len(splits) == 2924
    assert set(splits.values()) == set(range(5))
    assert splits == fold_map()
