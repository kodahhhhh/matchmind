import numpy as np
import pandas as pd
import pytest

from matchmind.models.backfill import join_outputs
from matchmind.models.common import data_dir


def test_uuid_aggregation_synthetic_skip_and_nullable_xt() -> None:
    actions = pd.DataFrame(
        {
            "action_id": [0, 1, 2, 3],
            "original_event_id": ["pass", "pass", None, "shot"],
            "vaep_value": [0.1, 0.2, 5, 0.4],
            "offensive_value": [0.2, 0.3, 6, 0.5],
            "defensive_value": [-0.1, -0.1, -1, -0.1],
        }
    )
    shots = pd.DataFrame({"original_event_id": ["shot"], "xg": [0.25]})
    xt = pd.DataFrame({"action_id": [0, 1, 2, 3], "xt": [np.nan, 0.2, 3, np.nan]})
    rows = join_outputs(actions, shots, xt).set_index("original_event_id")
    assert len(rows) == 2
    assert rows.loc["pass", "vaep"] == pytest.approx(0.3)
    assert rows.loc["pass", "xt"] == 0.2
    assert rows.loc["shot", "xg"] == 0.25
    assert pd.isna(rows.loc["pass", "xg"])
    assert pd.isna(rows.loc["shot", "xt"])


def test_world_cup_final_artifact_join() -> None:
    paths = [
        data_dir() / "processed/vaep/3869685.parquet",
        data_dir() / "processed/xt/3869685.parquet",
        data_dir() / "processed/xg/shots.parquet",
    ]
    if not all(p.exists() for p in paths):
        pytest.skip("Run model training to enable artifact integration test")
    actions, xt, shots = [pd.read_parquet(p) for p in paths]
    shots = shots[shots.game_id == 3869685]
    values = join_outputs(actions, shots, xt)
    goals = actions[
        actions.type_name.str.startswith("shot") & (actions.result_name == "success")
    ]
    assert len(goals[goals.period_id < 5]) == 6
    assert goals.original_event_id.isin(
        values[values.xg.notna()].original_event_id
    ).all()
    for kind, group in actions[actions.original_event_id.notna()].groupby("type_name"):
        assert group.original_event_id.isin(
            values[values.vaep.notna()].original_event_id
        ).all(), kind
    assert values.original_event_id.is_unique
