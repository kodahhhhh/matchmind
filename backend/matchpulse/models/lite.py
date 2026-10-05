"""Pure, source-independent outputs honestly supported by shots-only matches."""

from typing import Any

import numpy as np
import pandas as pd


def chance_summary(shots: pd.DataFrame) -> dict[str, Any]:
    """Observed chance totals; never possession, field tilt, VAEP or xT.

    Input xG must already be our model output. Minute bins retain coarse clocks,
    rather than manufacturing seconds or replay order. Unknown xG is not zero.
    """
    required = {"id", "team", "minute", "xg"}
    if not required.issubset(shots.columns):
        raise ValueError(
            f"Missing shot fields: {sorted(required - set(shots.columns))}"
        )
    if shots.id.duplicated().any() or not shots.team.isin(["home", "away"]).all():
        raise ValueError("Shots need unique evidence IDs and home/away sides")
    observed = shots.xg.dropna().to_numpy(dtype=float)
    if not np.isfinite(observed).all() or ((observed < 0) | (observed > 1)).any():
        raise ValueError("Own xG must be a probability")
    if "period" in shots:
        shots = shots[shots.period.isna() | (shots.period < 5)]
    teams = {}
    for side in ("home", "away"):
        g = shots[shots.team == side]
        teams[side] = {
            "shots_with_xg": int(g.xg.notna().sum()),
            "unscored_annotations": int(g.xg.isna().sum()),
            "xg": float(g.xg.sum()),
            "evidence_ids": g.loc[g.xg.notna(), "id"].tolist(),
        }
    total = sum(t["xg"] for t in teams.values())
    share = teams["home"]["xg"] / total if total > 0 else None
    bins = [
        {
            "team": side,
            "minute": int(minute),
            "xg": float(g.xg.sum()),
            "evidence_ids": g.loc[g.xg.notna(), "id"].tolist(),
        }
        for (side, minute), g in shots.groupby(["team", "minute"], sort=True)
    ]
    return {
        "teams": teams,
        "home_chance_share": share,
        "definition": "share of own shot xG, not possession or territorial control",
        "minute_bins": bins,
        "time_precision": "minute",
        "capabilities": {
            "shot_xg": True,
            "chance_totals": True,
            "vaep": False,
            "xt": False,
            "possession": False,
            "field_tilt": False,
            "pass_options": False,
            "substitution_effects": False,
        },
    }


def snapshot(
    shots: pd.DataFrame, *, period: int, minute: int, score: dict[str, int]
) -> dict[str, float]:
    """Strict pre-minute regulation snapshot with an independently known score.

    Require known shot periods; a minute-only Understat feed cannot resolve
    overlapping first-half stoppage and second-half clocks. Unknown-period rows
    must not be silently dropped. Seconds need not be guessed: whole current
    minute is excluded, identically during validation and inference.
    """
    if period not in (1, 2) or not (0 <= minute <= 90):
        raise ValueError("Only regulation-time outlook is supported")
    if period == 2 and minute < 45:
        raise ValueError("Second-half clock must start at minute 45")
    if "period" not in shots or shots.period.isna().any():
        raise ValueError("Verified shot periods are required for an outlook")
    if set(score) != {"home", "away"} or any(
        v < 0 or int(v) != v for v in score.values()
    ):
        raise ValueError("An independently verified nonnegative score is required")
    eligible = (shots.period < period) | (
        (shots.period == period) & (shots.minute < minute)
    )
    past = shots[eligible & (shots.period < 3)]
    if past.xg.isna().any():
        raise ValueError(
            "Exclude own-goal annotations; every genuine shot needs own xG"
        )
    result = {"minute": float(minute), "period": float(period)}
    for side in ("home", "away"):
        g = past[past.team == side]
        recent = g[(g.period == period) & (g.minute >= minute - 5)]
        result[f"score_{side}"] = float(score[side])
        result[f"xg_{side}"] = float(g.xg.sum())
        result[f"recent_xg_{side}"] = float(recent.xg.sum()) / 5
    result["score_diff"] = result["score_home"] - result["score_away"]
    return result
