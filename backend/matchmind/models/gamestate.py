"""Pure empirical game-state model over action DataFrames and saved neighbours.

No DB/HTTP access. Sixteen features use acting-team perspective. Future outcomes
are strictly after the anchor. Training windows require a complete horizon.
quantile_bands is the seam for a trained model to replace empirical quantiles.
"""

from typing import Any

import numpy as np
import pandas as pd

FEATURE_NAMES = (
    "minute",
    "score_diff",
    "possession",
    "field_tilt",
    "xg_for_rate",
    "xg_against_rate",
    "vaep_for_rate",
    "vaep_against_rate",
    "xt_for_rate",
    "xt_against_rate",
    "shots_for",
    "shots_against",
    "minutes_since_sub",
    "opponent_minutes_since_sub",
    "players_on_pitch",
    "opponent_players_on_pitch",
)
VERSION = "analog:v1"
CAVEAT = (
    "Learned from observational data: teams change their approach because of "
    "the score, so effects are confounded. Shown as a range next to real "
    "comparable situations, not a prediction."
)


def outcome_series(
    events: pd.DataFrame, markers: list[dict], anchor_t: float
) -> list[dict]:
    """Observed cumulative next-minute xG, goals and pass-share possession."""
    rows = []
    for minute in range(16):
        future = events[
            (events["t"] > anchor_t) & (events["t"] <= anchor_t + minute * 60)
        ]
        passes = future[future["type"].isin(("pass", "cross"))]
        total = len(passes)
        row = {}
        for side in ("home", "away"):
            own = future[future["team"] == side]
            row[side] = {
                "xg": round(float(own["xg"].sum()), 4),
                "possession": round(int((passes["team"] == side).sum()) / total, 4)
                if total
                else 0.5,
                "goals": sum(
                    m["type"] == "goal"
                    and m["team"] == side
                    and anchor_t < m["t"] <= anchor_t + minute * 60
                    for m in markers
                ),
            }
        rows.append(row)
    return rows


def state_features(
    events: pd.DataFrame,
    markers: list[dict],
    anchor: dict,
    team: str,
    model_values: dict,
) -> dict:
    """Five-minute lookback state at an arbitrary event, including subs/cards."""
    other = "away" if team == "home" else "home"
    end = anchor["t"]
    recent = events[
        (events["t"] > end - 300)
        & (events["t"] <= end)
        & (events["period"] == anchor["period"])
    ]
    passing = recent[recent["type"].isin(("pass", "cross"))]
    thirds = recent[
        recent["type"].isin(
            ("pass", "cross", "carry", "take_on", "shot", "shot_penalty")
        )
    ].copy()
    acting_x = np.where(
        thirds["team"] == "home", thirds["end_x"], 105 - thirds["end_x"]
    )
    thirds = thirds[acting_x > 70]
    scores = {
        s: sum(
            m["type"] == "goal" and m["team"] == s and m["t"] <= end for m in markers
        )
        for s in ("home", "away")
    }
    features: dict[str, Any] = {
        "minute": anchor["minute"],
        "score_diff": scores[team] - scores[other],
        "possession": float((passing["team"] == team).sum()) / len(passing)
        if len(passing)
        else 0.5,
        "field_tilt": float((thirds["team"] == team).sum()) / len(thirds)
        if len(thirds)
        else 0.5,
    }
    for side, tag in ((team, "for"), (other, "against")):
        own = recent[recent["team"] == side]
        features["xg_" + tag + "_rate"] = float(own["xg"].sum()) / 5
        features["vaep_" + tag + "_rate"] = float(own["vaep"].sum()) / 5
        # xT column is a gain, with positive threat gain as the row-level proxy.
        features["xt_" + tag + "_rate"] = (
            sum(
                model_values[e["id"]]["xt"]
                if model_values.get(e["id"], {}).get("xt") is not None
                else max(e["vaep"] or 0, 0)
                for e in own.to_dict("records")
            )
            / 5
        )
        features["shots_" + tag] = int(own["type"].str.startswith("shot").sum())
        subs = [
            m["t"]
            for m in markers
            if m["type"] == "sub" and m["team"] == side and m["t"] <= end
        ]
        cards = [
            m
            for m in markers
            if m["type"] == "card"
            and m["team"] == side
            and m["detail"] in ("red", "second_yellow")
            and m["t"] <= end
        ]
        prefix = "" if side == team else "opponent_"
        features[prefix + "minutes_since_sub"] = (
            (end - max(subs)) / 60 if subs else end / 60
        )
        features[prefix + "players_on_pitch"] = 11 - len(cards)
    features.update(
        {
            "period": anchor["period"],
            "t": end,
            "score_state": f"{scores[team] - scores[other]:+d}",
            "version": VERSION,
        }
    )
    return features


def build_windows(
    events: pd.DataFrame, markers: list[dict], match: dict, model_values: dict
) -> list[dict]:
    """Build both-team states every five elapsed minutes, with full future horizons."""
    rows = []
    for anchor_t in range(300, int(match["duration_t"] - 900) + 1, 300):
        past = events[events["t"] <= anchor_t]
        if past.empty:
            continue
        last = past.iloc[-1]
        anchor = {
            "period": int(last["period"]),
            "minute": int(last["minute"]),
            "t": float(anchor_t),
        }
        future = outcome_series(events, markers, float(anchor_t))
        for team in ("home", "away"):
            other = "away" if team == "home" else "home"
            series = [{"for": r[team], "against": r[other]} for r in future]
            rows.append(
                {
                    "window_id": f"{VERSION}:{match['match_id']}:{team}:{anchor_t}",
                    "match_id": match["match_id"],
                    "team": team,
                    "minute": anchor["minute"],
                    "features": state_features(
                        events, markers, anchor, team, model_values
                    ),
                    "outcome": {
                        "xg_for": series[-1]["for"]["xg"],
                        "xg_against": series[-1]["against"]["xg"],
                        "goals_for": series[-1]["for"]["goals"],
                        "goals_against": series[-1]["against"]["goals"],
                        "possession_for": series[-1]["for"]["possession"],
                        "possession_against": series[-1]["against"]["possession"],
                        "series": series,
                    },
                }
            )
    return rows


def standardize_windows(rows: list[dict]) -> tuple[list[dict], dict]:
    """Fit corpus means/scales once, then transform all feature vectors."""
    matrix = np.asarray(
        [[r["features"][k] for k in FEATURE_NAMES] for r in rows], dtype=float
    )
    mean, scale = matrix.mean(axis=0), matrix.std(axis=0)
    scale[scale < 1e-8] = 1
    for row, vector in zip(rows, (matrix - mean) / scale, strict=True):
        row["embedding"] = vector.tolist()
    return rows, {
        "version": VERSION,
        "names": list(FEATURE_NAMES),
        "mean": mean.tolist(),
        "scale": scale.tolist(),
    }


def changed_features(
    features: dict, marker: dict, markers: list[dict], change: str
) -> dict:
    """Apply supported intervention to state; caller validates marker/change pairing."""
    result = dict(features)
    if change == "remove_goal":
        result["score_diff"] -= 1
    elif change == "no_sub":
        earlier = [
            m["t"]
            for m in markers
            if m["type"] == "sub"
            and m["team"] == marker["team"]
            and m["t"] < marker["t"]
        ]
        result["minutes_since_sub"] = (
            (marker["t"] - max(earlier)) / 60 if earlier else marker["t"] / 60
        )
    elif change == "remove_red_card":
        result["players_on_pitch"] += 1
    return result


def standardized_vector(features: dict, scaling: dict) -> list[float]:
    """Use saved corpus scaling for requests; never fit on the request itself."""
    return [
        (features[k] - mean) / scale
        for k, mean, scale in zip(
            scaling["names"], scaling["mean"], scaling["scale"], strict=True
        )
    ]


def quantile_bands(
    neighbours: list[dict],
    side: str,
    offset: int,
    metric: str,
    state: dict | None = None,
) -> dict:
    """Empirical bands; W6 can predict from the changed `state` at this seam."""
    values = [r["outcome"]["series"][offset][side][metric] for r in neighbours]
    return {
        key: round(float(v), 4)
        for key, v in zip(
            ("p10", "p50", "p90"), np.quantile(values, [0.1, 0.5, 0.9]), strict=True
        )
    }


def counterfactual_response(
    match: dict,
    marker: dict,
    change: str,
    actual: list[dict],
    neighbours: list[dict],
    state: dict | None = None,
) -> dict:
    """Serialize real neighbours and empirical bands into the fixed UI contract."""
    focus = marker["team"]

    def band(side: str, offset: int, metric: str) -> dict:
        return quantile_bands(
            neighbours, "for" if side == focus else "against", offset, metric, state
        )

    analogs = []
    for row in neighbours[:5]:
        m = row["meta"]
        outcome = row["outcome"]
        analogs.append(
            {
                "match_id": row["match_id"],
                "competition": m["competition"],
                "season": m["season"],
                "home": m["home"]["name"],
                "away": m["away"]["name"],
                "minute": row["minute"],
                "score_state": row["features"]["score_state"],
                "similarity": round(1 / (1 + row["distance"]), 4),
                "next15": {
                    k: outcome[k]
                    for k in ("xg_for", "xg_against", "goals_for", "goals_against")
                },
            }
        )
    caps = {1: 45, 2: 90, 3: 105, 4: 120}
    shown = marker["minute"] + 1
    cap = caps[marker["period"]]
    label = f"{cap}+{shown - cap}'" if shown > cap else f"{shown}'"
    return {
        "match_id": match["match_id"],
        "event_id": marker["event_id"],
        "change": change,
        "label": "Modelled hypothetical",
        "horizon_minutes": 15,
        "anchor": {
            "period": marker["period"],
            "minute": marker["minute"],
            "label": label,
        },
        "actual": actual[-1],
        "modelled": {
            s: {"xg": band(s, 15, "xg"), "possession": band(s, 15, "possession")}
            for s in ("home", "away")
        },
        "series": [
            {
                "offset_min": i,
                "actual": {s: actual[i][s]["xg"] for s in ("home", "away")},
                "modelled": {s: band(s, i, "xg") for s in ("home", "away")},
            }
            for i in range(16)
        ],
        "analogs": analogs,
        "n_analogs": len(neighbours),
        "caveat": CAVEAT,
    }
