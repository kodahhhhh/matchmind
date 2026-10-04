"""Model fallbacks, elapsed time, interventions and grounding edge cases."""

import asyncio
from copy import deepcopy
from unittest.mock import patch

import pandas as pd

from matchmind.analyst.agent import ask_chunks
from matchmind.analyst.grounding import display_evidence, grounding_errors, sentences
from matchmind.metrics.match import compute_match
from matchmind.models.gamestate import (
    FEATURE_NAMES,
    changed_features,
    outcome_series,
    standardize_windows,
    standardized_vector,
)


def test_model_columns_override_proxies_without_changing_public_shape() -> None:
    raw = [
        {
            "index": 1,
            "type": {"name": "Pass"},
            "pass": {"end_location": [100, 40], "body_part": {"name": "Left Foot"}},
            "period": 1,
            "minute": 0,
            "second": 0,
            "player": {"id": 1},
            "team": {"name": "Home"},
            "possession": 1,
            "possession_team": {"name": "Home"},
            "location": [60, 40],
        },
        {
            "index": 2,
            "type": {"name": "Shot"},
            "shot": {
                "type": {"name": "Open Play"},
                "outcome": {"name": "Goal"},
                "statsbomb_xg": 0.2,
                "end_location": [120, 40],
            },
            "period": 1,
            "minute": 0,
            "second": 5,
            "player": {"id": 1},
            "team": {"name": "Home"},
            "possession": 1,
            "possession_team": {"name": "Home"},
            "location": [100, 40],
        },
    ]
    cat = {
        "match_id": "sb:1",
        "home": {"id": 1, "name": "Home"},
        "away": {"id": 2, "name": "Away"},
        "competition": "Test",
        "season": "2026",
        "stage": None,
        "match_date": None,
        "kick_off": None,
        "reconstructed": True,
        "home_score": 1,
        "away_score": 0,
        "lineups": [
            {
                "team_name": "Home",
                "lineup": [
                    {
                        "player_id": 1,
                        "player_name": "Player",
                        "player_nickname": None,
                        "jersey_number": 1,
                        "positions": [
                            {"position": "Forward", "start_reason": "Starting XI"}
                        ],
                    }
                ],
            }
        ],
    }
    frame = pd.DataFrame(
        [
            {
                "event_id": f"sb:1:{r['index']}",
                "extra": r,
                "xg": None,
                "vaep": None,
                "vaep_off": None,
                "vaep_def": None,
                "xt": None,
            }
            for r in raw
        ]
    )
    fallback = compute_match(frame, cat)
    assert fallback["events"][-1]["xg"] == 0.2
    updated = frame.copy()
    updated["xg"] = [None, 0.8]
    updated["vaep"] = [0.0, -0.2]
    updated["vaep_off"] = [0.3, 0.4]
    updated["vaep_def"] = [-0.1, -0.2]
    real = compute_match(updated, cat)
    assert real["events"][0]["vaep"] == 0.0
    assert real["events"][-1]["xg"] == 0.8
    assert real["events"][-1]["sb_xg"] == 0.2
    assert real["events"][-1]["vaep"] == -0.2
    p = real["players"][0]
    assert p["vaep"] == -0.2 and p["vaep_off"] == 0.7 and p["vaep_def"] == -0.3
    assert fallback["events"][0].keys() == real["events"][0].keys()


def test_saved_feature_scaling_and_interventions() -> None:
    rows = [
        {"features": {k: float(i + j) for j, k in enumerate(FEATURE_NAMES)}}
        for i in range(4)
    ]
    transformed, scaling = standardize_windows(deepcopy(rows))
    assert len(scaling["names"]) == 16
    for a, b in zip(rows, transformed, strict=True):
        assert standardized_vector(a["features"], scaling) == b["embedding"]
    state = {"score_diff": 0, "minutes_since_sub": 0.0, "players_on_pitch": 10}
    marker = {"team": "home", "t": 500.0}
    assert changed_features(state, marker, [], "remove_goal")["score_diff"] == -1
    assert (
        changed_features(
            state, marker, [{"type": "sub", "team": "home", "t": 200.0}], "no_sub"
        )["minutes_since_sub"]
        == 5
    )
    assert (
        changed_features(state, marker, [], "remove_red_card")["players_on_pitch"] == 11
    )
    assert state["score_diff"] == 0


def test_future_excludes_anchor_event() -> None:
    events = pd.DataFrame(
        [
            {"t": 60.0, "team": "home", "type": "shot", "xg": 0.8},
            {"t": 65.0, "team": "away", "type": "shot", "xg": 0.1},
        ]
    )
    rows = outcome_series(events, [{"type": "goal", "team": "home", "t": 60.0}], 60.0)
    assert rows[-1]["home"]["xg"] == 0 and rows[-1]["home"]["goals"] == 0
    assert rows[-1]["away"]["xg"] == 0.1


def test_decimal_split_and_invalid_claims() -> None:
    parts, rest = sentences("France produced 0.")
    assert parts == [] and rest == "France produced 0."
    parts, rest = sentences(rest + "617 xG. More")
    assert parts == ["France produced 0.617 xG. "] and rest == "More"
    result = {"xg": 0.617, "field_tilt": 0.377, "id": "sb:3869685:2928"}
    result["display_numbers"] = display_evidence(result)
    assert not any(
        grounding_errors("0.62 xG, 38% tilt. [[ev:sb:3869685:2928]]", [result]).values()
    )
    assert grounding_errors("3869685 shots", [result])["unsupported_numbers"] == [
        "3869685"
    ]
    assert grounding_errors("0.7 xG [[ev:sb:3869685:5]]", [result]) == {
        "unsupported_numbers": ["0.7"],
        "unsupported_citations": ["ev:sb:3869685:5"],
        "unsupported_units": ["0.7 xG"],
        "forbidden_phrasing": [],
    }


def test_unit_claims_and_forbidden_phrasing() -> None:
    result = {"home": {"shots": 2, "xg": 0.339}, "away": {"passes": 51}, "minute": 3}
    assert not any(
        grounding_errors("France had 2 shots and 0.339 xG.", [result]).values()
    )
    # 3 is in the output (a minute), but never as a shot count.
    errors = grounding_errors("France had 3 shots.", [result])
    assert errors["unsupported_units"] == ["3 shots"]
    assert errors["unsupported_numbers"] == []
    assert not grounding_errors("Messi made 51 progressive passes.", [result])[
        "unsupported_units"
    ]
    assert grounding_errors("A miss would have helped.", [result])[
        "forbidden_phrasing"
    ] == ["would have"]
    assert grounding_errors("It wouldn't have mattered.", [result])[
        "forbidden_phrasing"
    ] == ["wouldn't have"]


def test_ask_provider_error_finishes_cleanly() -> None:
    async def collect() -> list:
        with patch(
            "matchmind.analyst.agent.async_client",
            side_effect=RuntimeError("private provider payload"),
        ):
            return [
                c async for c in ask_chunks("sb:3869685", "Find the turning point", [])
            ]

    chunks = asyncio.run(collect())
    assert chunks[-1] == {"type": "done"}
    assert any(c["type"] == "text" for c in chunks)
    assert "private provider payload" not in str(chunks)


def test_counterfactual_model_seam_receives_intervention_state() -> None:
    from matchmind.api.counterfactual import run_counterfactual
    from matchmind.models.gamestate_model import predict

    observed = []

    def inspect(state: pd.DataFrame) -> dict:
        observed.append(state.copy())
        return predict(state)

    with patch("matchmind.api.counterfactual.predict", side_effect=inspect):
        result = run_counterfactual("sb:3869685", "sb:3869685:2928", "remove_goal")
    assert result["label"] == "Modelled hypothetical"
    assert result["method"] == "trained_model"
    # Changed state first, then the same model on the real (factual) state.
    assert len(observed) == 2
    assert observed[0].score_diff.tolist() == [2, -2]
    assert observed[1].score_diff.tolist() == [1, -1]
    assert result["effect"]["home"]["xg"] == round(
        result["modelled"]["home"]["xg"]["p50"]
        - result["factual"]["home"]["xg"]["p50"],
        4,
    )
