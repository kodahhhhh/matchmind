"""Trained what-if acceptance: training parity, interventions and full corpus."""

import json

import numpy as np
import pandas as pd
import pytest

from matchmind.api.counterfactual import (
    inference_inputs,
    model_metadata,
    run_counterfactual,
    training_analogs,
)
from matchmind.api.repository import require_match
from matchmind.models.common import data_dir
from matchmind.models.gamestate_model import (
    FEATURES,
    anchor_features,
    intervene,
    match_context,
    predict,
)

FINAL = "sb:3869685"


def test_all_saved_final_windows_match_inference_features() -> None:
    actions, context = inference_inputs(FINAL)
    saved = pd.read_parquet(data_dir() / "processed/gamestate_windows.parquet")
    saved = saved[saved.match_id == FINAL]
    for _, row in saved[saved.team == "home"].iterrows():
        anchor = {
            "t": row.elapsed_end_seconds,
            "period": int(row.period),
            "local_seconds": row.elapsed_end_seconds - context["offsets"][row.period],
        }
        features = anchor_features(
            actions, context, anchor, require_match(FINAL), include_anchor=False
        )
        for i, side in enumerate(("home", "away")):
            expected = saved[
                (saved.team == side) & (saved.elapsed_end_seconds == anchor["t"])
            ].iloc[0]
            np.testing.assert_allclose(
                features.iloc[i], expected[FEATURES].astype(float), atol=1e-12
            )


def test_arbitrary_anchor_uses_spadl_start_positions_and_period_local_sums() -> None:
    actions = pd.DataFrame(
        {
            "elapsed": [280, 300, 320, 320, 321],
            "period_id": [1, 2, 2, 2, 2],
            "source_index": [1, 2, 3, 4, 5],
            "team_id": [1, 1, 2, 1, 2],
            "start_x": [90, 80, 75, 10, 90],
            "is_pass": [False, True, False, False, False],
            "is_shot": [True, False, True, False, True],
            "xg": [9, 0, 0.4, 0, 8],
            "vaep_value": [9, 0.2, 0.3, 7, 8],
            "xt": [9, np.nan, 0.05, 7, 8],
        }
    )
    anchor = {"t": 320, "index": 3, "period": 2, "local_seconds": 20}
    match = {"home": {"id": 1}, "away": {"id": 2}, "competition": "UEFA Euro"}
    frame = anchor_features(actions, {"markers": []}, anchor, match)
    assert list(frame) == FEATURES
    assert frame.xg_for.tolist() == [0, 0.4]
    assert frame.vaep_for.tolist() == [0.2, 0.3]
    assert frame.possession_share.tolist() == [1, 0]
    assert frame.field_tilt.tolist() == [0.5, 0.5]
    assert frame.xt_for_rate.tolist() == [0, 0.01]
    assert frame.minute.iloc[0] == pytest.approx(45 + 20 / 60)


@pytest.mark.parametrize("side", ["home", "away"])
@pytest.mark.parametrize("change", ["remove_goal", "no_sub", "remove_red_card"])
def test_interventions_only_change_affected_features(side: str, change: str) -> None:
    factual = pd.DataFrame([dict.fromkeys(FEATURES, 0.0)] * 2)
    factual["players_for"], factual["players_against"] = [10, 9], [9, 10]
    original = factual.copy(deep=True)
    anchor = {"team": side, "t": 600, "index": 12, "event_id": "sb:1:12"}
    context = {
        "markers": [
            {"type": "sub", "team": side, "t": 180, "index": 4},
            {"type": "sub", "team": side, "t": 600, "index": 12},
            {"type": "sub", "team": side, "t": 600, "index": 13},
            {"type": "red", "event_id": "sb:1:12"},
        ]
    }
    result = intervene(factual, anchor, context, change)
    own, opp = (0, 1) if side == "home" else (1, 0)
    expected = original.copy()
    if change == "remove_goal":
        expected.loc[own, "score_diff"] = -1
        expected.loc[opp, "score_diff"] = 1
    elif change == "no_sub":
        expected.loc[own, "minutes_since_sub"] = 7
        expected.loc[opp, "minutes_since_opponent_sub"] = 7
    else:
        expected.loc[own, "players_for"] += 1
        expected.loc[opp, "players_against"] += 1
    pd.testing.assert_frame_equal(result, expected.astype(float))
    pd.testing.assert_frame_equal(factual, original)


def test_no_sub_swaps_player_ratings_back() -> None:
    frame = pd.DataFrame([dict.fromkeys(FEATURES, 0.0)] * 2)
    frame["lineup_vaep_for"], frame["lineup_vaep_against"] = [1.5, 1.4], [1.4, 1.5]
    frame["players_for"] = frame["players_against"] = 11
    anchor = {"team": "away", "t": 600, "index": 12, "event_id": "sb:1:12"}
    context = {
        "markers": [
            {
                "type": "sub",
                "team": "away",
                "t": 600,
                "index": 12,
                "event_id": "sb:1:12",
                "player_off": 7,
                "player_on": 8,
            }
        ]
    }
    changed = intervene(frame, anchor, context, "no_sub", {7: 0.4, 8: 0.1})
    assert changed.lineup_vaep_for.tolist() == pytest.approx([1.5, 1.7])
    assert changed.lineup_vaep_against.tolist() == pytest.approx([1.7, 1.5])


def test_sub_without_prior_and_bench_red() -> None:
    frame = pd.DataFrame([dict.fromkeys(FEATURES, 0.0)] * 2)
    frame["players_for"] = frame["players_against"] = 11
    anchor = {"team": "home", "t": 600, "index": 12, "event_id": "sb:1:12"}
    context = {"markers": []}
    changed = intervene(frame, anchor, context, "no_sub")
    assert changed.minutes_since_sub.iloc[0] == 10
    assert changed.minutes_since_opponent_sub.iloc[1] == 10
    pd.testing.assert_frame_equal(
        intervene(frame, anchor, context, "remove_red_card"), frame.astype(float)
    )


def test_context_counts_only_on_pitch_unique_dismissals() -> None:
    raw = [
        {
            "type": {"name": "Starting XI"},
            "tactics": {"lineup": [{"player": {"id": 10}}]},
        },
        {
            "type": {"name": "Bad Behaviour"},
            "player": {"id": 99},
            "bad_behaviour": {"card": {"name": "Red Card"}},
        },
        {
            "type": {"name": "Foul Committed"},
            "player": {"id": 10},
            "foul_committed": {"card": {"name": "Second Yellow"}},
        },
        {
            "type": {"name": "Bad Behaviour"},
            "player": {"id": 10},
            "bad_behaviour": {"card": {"name": "Red Card"}},
        },
    ]
    for i, row in enumerate(raw):
        row.update(index=i, period=1, minute=0, timestamp=f"00:00:0{i}", team={"id": 1})
    context = match_context(
        raw, {"match_id": "sb:1", "home": {"id": 1}, "away": {"id": 2}}
    )
    assert len(context["markers"]) == 1
    assert context["markers"][0]["event_id"] == "sb:1:2"


def test_index_is_exact_complete_and_excludes_match() -> None:
    index = training_analogs()
    assert len(index.windows) == 89450
    assert index.windows.match_id.nunique() == 2924
    assert (index.windows.horizon_seconds >= 900).all()
    assert (index.windows.future_passes > 0).all()
    query = index.windows[index.windows.match_id == FINAL].iloc[[0]][FEATURES]
    rows = index.nearest(query, FINAL)
    matrix = (index.windows[FEATURES].to_numpy() - index.mean) / index.scale
    vector = (query.to_numpy()[0] - index.mean) / index.scale
    distances = np.linalg.norm(matrix - vector, axis=1)
    distances[index.match_ids == FINAL] = np.inf
    expected = np.sort(distances)[:40]
    np.testing.assert_allclose([r["distance"] for r in rows], expected)
    assert all(r["match_id"] != FINAL for r in rows)


def test_response_uses_trained_bands_and_observed_analog_summary() -> None:
    event_id = "sb:3869685:2928"
    actions, context = inference_inputs(FINAL)
    anchor = context["anchors"][event_id]
    factual = anchor_features(actions, context, anchor, require_match(FINAL))
    changed = intervene(factual, anchor, context, "remove_goal")
    expected = predict(changed)
    response = run_counterfactual(FINAL, event_id, "remove_goal")
    assert response["method"] == "trained_model"
    assert response["model"] == model_metadata()
    report = json.loads((data_dir() / "models/gamestate.json").read_text())
    assert (
        response["model"]["coverage_p10_p90"]["xg"]
        == report["metrics"]["xg_for"]["coverage_p10_p90"]
    )
    rows = training_analogs().nearest(changed.iloc[[1]], FINAL)
    for i, side in enumerate(("home", "away")):
        for metric, target in (("xg", "xg_for"), ("possession", "possession_share")):
            assert response["modelled"][side][metric] == {
                q: v[i] for q, v in expected[target].items()
            }
        outcome = "outcome_xg_for" if side == "away" else "outcome_xg_against"
        np.testing.assert_allclose(
            list(response["analog_summary"][side]["xg"].values()),
            np.quantile([r[outcome] for r in rows], [0.1, 0.5, 0.9]),
        )
    assert all(point["modelled"] is None for point in response["series"])
    assert all(0 <= row["similarity"] <= 1 for row in response["analogs"])
