"""Counterfactual orchestration: DB neighbours in, pure model computation out."""

import pandas as pd
from fastapi import HTTPException

from matchmind.api.repository import bundle, connect
from matchmind.models.gamestate import (
    VERSION,
    changed_features,
    counterfactual_response,
    outcome_series,
    standardized_vector,
    state_features,
)


def run_counterfactual(match_id: str, event_id: str, change: str) -> dict:
    """Validate intervention, query forty real analogs and return empirical bands."""
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
    events = pd.DataFrame(b["events"])
    features = state_features(
        events, b["match"]["markers"], marker, marker["team"], b["model_values"]
    )
    changed = changed_features(features, marker, b["match"]["markers"], change)
    with connect() as conn:
        scaling = conn.execute(
            "SELECT scaling FROM gamestate_scaling WHERE version=%s", (VERSION,)
        ).fetchone()
        if not scaling:
            raise HTTPException(503, "Empirical analog windows have not been loaded")
        vector = str(standardized_vector(changed, scaling["scaling"]))
        conn.execute("SET LOCAL hnsw.ef_search=200")
        rows = conn.execute(
            "SELECT w.*,m.meta,w.embedding <-> %s::vector AS distance FROM "
            "gamestate_windows w JOIN matches m USING(match_id) WHERE "
            "w.match_id<>%s AND w.window_id LIKE %s ORDER BY w.embedding <-> "
            "%s::vector LIMIT 40",
            (vector, match_id, VERSION + ":%", vector),
        ).fetchall()
    if not rows:
        raise HTTPException(503, "No empirical analogs available")
    actual = outcome_series(events, b["match"]["markers"], marker["t"])
    return counterfactual_response(b["match"], marker, change, actual, rows)
