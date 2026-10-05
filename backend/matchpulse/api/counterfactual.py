"""Counterfactual artifact loading and orchestration; no analytics in the route.

One exact in-memory 19D index per API process covers all training matches. It
avoids changing the legacy vector(16) DB table used by the refresh command.
Immutable training artifacts are cached for the process lifetime; restart after
replacing them. Per-match SPADL inputs are bounded to 128 cached matches.
"""

import json
from functools import lru_cache

import pandas as pd
from fastapi import HTTPException

from matchpulse.api.repository import bundle, require_match
from matchpulse.models.common import data_dir, raw_events
from matchpulse.models.gamestate import (
    TrainingAnalogs,
    counterfactual_response,
    outcome_series,
)
from matchpulse.models.gamestate_model import (
    anchor_features,
    intervene,
    match_context,
    player_ratings,
    predict,
    prepare_actions,
)


@lru_cache(maxsize=1)
def training_analogs() -> TrainingAnalogs:
    """Build an exact, standardized index once from complete training horizons."""
    return TrainingAnalogs(
        pd.read_parquet(data_dir() / "processed/gamestate_windows.parquet")
    )


@lru_cache(maxsize=1)
def model_metadata() -> dict:
    """Use measured coverage and training size, never fixture/example numbers."""
    report = json.loads((data_dir() / "models/gamestate.json").read_text())
    return {
        "name": "Game-state quantile model (LightGBM)",
        "trained_matches": report["n_matches"],
        "coverage_p10_p90": {
            "xg": report["metrics"]["xg_for"]["coverage_p10_p90"],
            "possession": report["metrics"]["possession_share"]["coverage_p10_p90"],
        },
        # Share of the constant-range baseline's median error the model removes.
        "skill_vs_constant": {
            key: round(
                1
                - report["metrics"][target]["pinball"]["p50"]
                / report["baselines"][target]["constant"]["pinball"]["p50"],
                4,
            )
            for key, target in (("xg", "xg_for"), ("possession", "possession_share"))
        },
    }


@lru_cache(maxsize=1)
def shot_values() -> pd.DataFrame:
    """Read just the held-out shot values used by the window training pipeline."""
    return pd.read_parquet(
        data_dir() / "processed/xg/shots.parquet",
        columns=["game_id", "original_event_id", "xg"],
    )


@lru_cache(maxsize=128)
def inference_inputs(match_id: str) -> tuple[pd.DataFrame, dict]:
    """Load saved SPADL/OOF artifacts; raw timestamps establish the training clock."""
    match = require_match(match_id)
    native = match["native_id"]
    raw = raw_events(native)
    context = match_context(raw, match)
    actions = prepare_actions(
        pd.read_parquet(data_dir() / f"processed/vaep/{native}.parquet"),
        pd.read_parquet(data_dir() / f"processed/xt/{native}.parquet"),
        shot_values().loc[lambda rows: rows.game_id == native],
        raw,
        match,
        context,
    )
    return actions, context


@lru_cache(maxsize=2924)
def analog_goal_history(match_id: str, home: str) -> list[dict]:
    """Load only local goal history for top-five analogs, including non-demo games."""
    from matchpulse.models.common import event_clock, event_seconds

    raw = raw_events(int(match_id.split(":")[1]))
    offsets, _ = event_clock(raw)
    goals = []
    for event in raw:
        if event["period"] == 5:
            continue
        kind = event["type"]["name"]
        if not (
            (kind == "Shot" and event["shot"]["outcome"]["name"] == "Goal")
            or kind == "Own Goal Against"
        ):
            continue
        side = "home" if event["team"]["name"] == home else "away"
        if kind == "Own Goal Against":
            side = "away" if side == "home" else "home"
        goals.append(
            {"t": offsets[event["period"]] + event_seconds(event), "team": side}
        )
    return goals


def run_counterfactual(match_id: str, event_id: str, change: str) -> dict:
    """Predict each team's modified state and retrieve forty full-corpus analogs."""
    b = bundle(match_id)
    marker = next((m for m in b["match"]["markers"] if m["event_id"] == event_id), None)
    if marker is None:
        raise HTTPException(
            422, "Choose a goal, substitution or red-card event in this match"
        )
    valid = (
        (change == "remove_goal" and marker["type"] == "goal")
        or (change == "no_sub" and marker["type"] == "sub")
        or (
            change == "remove_red_card"
            and marker["type"] == "card"
            and marker["detail"] in ("red", "second_yellow")
        )
    )
    if not valid:
        raise HTTPException(422, "Change does not match the selected event")
    try:
        actions, context = inference_inputs(match_id)
        anchor = {**context["anchors"][event_id], "team": marker["team"]}
        match = require_match(match_id)
        ratings = player_ratings(context, match)
        factual = anchor_features(actions, context, anchor, match)
        changed = intervene(factual, anchor, context, change, ratings)
        predictions = predict(changed)
        baseline = predict(factual)
        outlook = result_outlook(b, marker, change, factual, changed, match)
        metadata = model_metadata()
        focus = 0 if marker["team"] == "home" else 1
        neighbours = training_analogs().nearest(changed.iloc[[focus]], match_id)
        goals = {
            r["match_id"]: analog_goal_history(r["match_id"], r["home"])
            for r in neighbours[:5]
        }
    except FileNotFoundError as exc:
        raise HTTPException(
            503, "Trained game-state artifacts are unavailable"
        ) from exc
    if not neighbours:
        raise HTTPException(503, "No complete historical analogs available")
    actual = outcome_series(
        pd.DataFrame(b["events"]), b["match"]["markers"], marker["t"]
    )
    return counterfactual_response(
        b["match"],
        marker,
        change,
        actual,
        neighbours,
        predictions,
        metadata,
        goals,
        factual=baseline,
        lineup_change=lineup_change(b, context, event_id, ratings),
        outlook=outlook,
    )


def result_outlook(
    b: dict,
    marker: dict,
    change: str,
    factual: pd.DataFrame,
    changed: pd.DataFrame,
    match: dict,
) -> dict:
    """Score at the anchor (with and without the change) and the goals model's view."""
    from matchpulse.models.goals import knockout, outlook

    index = int(marker["event_id"].split(":")[2])
    score = {"home": 0, "away": 0}
    for m in b["match"]["markers"]:
        if m["type"] == "goal" and int(m["event_id"].split(":")[2]) <= index:
            score[m["team"]] += 1
    changed_score = dict(score)
    if change == "remove_goal":
        changed_score[marker["team"]] -= 1
    return outlook(
        factual, changed, marker["period"], score, changed_score, knockout(match)
    )


def lineup_change(
    b: dict, context: dict, event_id: str, ratings: dict[int, float]
) -> dict | None:
    """Who the intervention puts back on the pitch, with the ratings it swaps."""
    names = {
        p["player_id"]: p["short_name"]
        for side in b["match"]["lineups"].values()
        for p in side
    }

    def rated(player_id: int) -> dict:
        return {
            "player_id": player_id,
            "name": names.get(player_id, str(player_id)),
            "vaep_per90": round(ratings[player_id], 4),
        }

    for m in context["markers"]:
        if m["event_id"] != event_id:
            continue
        if m["type"] == "sub":
            return {
                "restored": rated(m["player_off"]),
                "removed": rated(m["player_on"]),
            }
        if m["type"] == "red":
            return {"restored": rated(m["player"]), "removed": None}
    return None
