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


def test_vaep_retains_score_across_half_time() -> None:
    import pandas as pd

    from matchmind.models.common import data_dir

    path = data_dir() / "processed/vaep_features/3869685.parquet"
    if not path.exists():
        pytest.skip("SPADL feature artifacts not generated")
    features = pd.read_parquet(path)
    actions = pd.read_parquet(data_dir() / "processed/spadl/3869685.parquet")
    first_second_half = actions[actions.period_id == 2].iloc[0]
    row = features[features.action_id == first_second_half.action_id].iloc[0]
    argentina_has_ball = first_second_half.team_id == 779
    assert row.goalscore_team == (2 if argentina_has_ball else 0)
    assert row.goalscore_opponent == (0 if argentina_has_ball else 2)
