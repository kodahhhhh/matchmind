import numpy as np
import pandas as pd
import pytest

from matchpulse.models.gamestate_model import FEATURES, bound_predictions, featurize
from matchpulse.models.windows import event_clock


def test_feature_contract_and_missing_values() -> None:
    row = dict.fromkeys(FEATURES, 0)
    frame = featurize([{"features": row, "outcome_xg_for": 900}])
    assert list(frame.columns) == FEATURES
    with pytest.raises(ValueError, match="Missing"):
        featurize([{"minute": 10}])
    row["minute"] = np.nan
    with pytest.raises(ValueError, match="finite"):
        featurize([row])


def test_quantile_order_and_support() -> None:
    p = bound_predictions(np.array([[1.2, -0.1, 0.5]]), "possession_share")
    np.testing.assert_allclose(p, [[0, 0.5, 1]])


def test_clock_does_not_overlap_stoppage_and_second_half() -> None:
    events = [
        {"period": 1, "timestamp": "00:48:00"},
        {"period": 2, "timestamp": "00:47:00"},
        {"period": 5, "timestamp": "00:12:00"},
    ]
    offsets, lengths = event_clock(events)
    assert offsets == {1: 0, 2: 48 * 60}
    assert sum(lengths.values()) == 95 * 60


def test_counterfactual_copy_preserves_factual_features() -> None:
    factual = pd.DataFrame([dict.fromkeys(FEATURES, 0)])
    changed = featurize(factual).copy()
    changed["score_diff"] -= 1
    assert factual.score_diff.iloc[0] == 0
    assert changed.score_diff.iloc[0] == -1


def test_window_boundaries_and_substitution_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import matchpulse.models.windows as windows

    events = [
        {
            "period": 1,
            "timestamp": "00:00:00",
            "type": {"name": "Starting XI"},
            "team": {"id": 1},
            "tactics": {"lineup": [{"player": {"id": 10}}]},
        },
        {
            "period": 1,
            "timestamp": "00:00:00",
            "type": {"name": "Starting XI"},
            "team": {"id": 2},
            "tactics": {"lineup": [{"player": {"id": 20}}]},
        },
        {
            "period": 1,
            "timestamp": "00:02:00",
            "type": {"name": "Substitution"},
            "team": {"id": 1},
            "player": {"id": 10},
            "substitution": {"replacement": {"id": 11}},
        },
        {
            "period": 1,
            "timestamp": "00:06:00",
            "type": {"name": "Bad Behaviour"},
            "team": {"id": 2},
            "player": {"id": 20},
            "bad_behaviour": {"card": {"name": "Red Card"}},
        },
        {
            "period": 1,
            "timestamp": "00:30:00",
            "type": {"name": "Half End"},
            "team": {"id": 1},
        },
    ]
    actions = pd.DataFrame(
        {
            "game_id": [99] * 4,
            "period_id": [1] * 4,
            "time_seconds": [100, 299, 300, 301],
            "team_id": [1, 1, 1, 2],
            "start_x": [50, 90, 90, 30],
            "end_x": [70, 105, 105, 20],
            "start_y": [34] * 4,
            "end_y": [34] * 4,
            "original_event_id": ["pass", "before", "after", "away"],
            "type_name": ["goalkick", "shot", "shot", "pass"],
            "vaep_value": [0.1, 0.2, 0.9, -0.1],
        }
    )
    shots = pd.DataFrame({"original_event_id": ["before", "after"], "xg": [0.2, 0.8]})
    monkeypatch.setattr(windows, "_SHOTS", {99: shots})
    monkeypatch.setattr(windows, "_MODELS", {})
    monkeypatch.setattr(windows, "_XT", None)
    monkeypatch.setattr(windows, "raw_events", lambda _: events)
    actions["action_id"] = range(len(actions))
    actions["xt"] = 0.0
    monkeypatch.setattr(windows.pd, "read_parquet", lambda _: actions.copy())
    match = {
        "native_id": 99,
        "match_id": "sb:99",
        "home": {"id": 1, "name": "A"},
        "away": {"id": 2, "name": "B"},
        "competition": "UEFA Euro",
        "season": "2024",
        "match_date": None,
        "reconstructed": False,
    }
    frame = windows.build_match(match)
    home = frame[(frame.team == "home") & (frame.minute == 5)].iloc[0]
    assert home.possession_share == 1.0
    assert home.xg_for == pytest.approx(0.2)
    assert home.outcome_xg_for == pytest.approx(0.8)
    assert home.vaep_for == pytest.approx(0.3)
    assert home.minutes_since_sub == 3
    assert home.players_against == 11
    later = frame[(frame.team == "home") & (frame.minute == 10)].iloc[0]
    assert later.players_against == 10
    assert frame.iloc[-1].horizon_seconds == 0
