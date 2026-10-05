"""Pure historical analog retrieval and trained counterfactual serialization.

TrainingAnalogs uses all 19 trained features and complete future horizons.
Legacy 16-feature helpers remain compatible with the DB refresh command.
No DB or HTTP access.
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
    "Estimated from what usually happened next in similar real matches. Goals, "
    "substitutions and red cards don't happen at random, so treat this as a "
    "guide to the odds, not a certainty."
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


class TrainingAnalogs:
    """Exact 19-feature in-memory neighbours over complete OOF training windows.

    Fit scaling once on eligible training rows, never on a request. A cKDTree
    avoids the legacy DB's incompatible vector(16); metadata needs no DB replay.
    """

    def __init__(self, windows: pd.DataFrame) -> None:
        from scipy.spatial import cKDTree

        from matchpulse.models.gamestate_model import featurize

        self.windows = windows[
            (windows.horizon_seconds >= 900) & (windows.future_passes > 0)
        ].reset_index(drop=True)
        matrix = featurize(self.windows).to_numpy()
        self.mean, self.scale = matrix.mean(axis=0), matrix.std(axis=0)
        self.scale[self.scale < 1e-8] = 1
        self.tree = cKDTree((matrix - self.mean) / self.scale)
        self.match_ids = self.windows.match_id.to_numpy()

    def nearest(self, state: pd.DataFrame, match_id: str, k: int = 40) -> list[dict]:
        """Return exact nearest rows, excluding every perspective of this match."""
        from matchpulse.models.gamestate_model import featurize

        vector = (featurize(state).to_numpy()[0] - self.mean) / self.scale
        count = min(len(self.windows), k + int((self.match_ids == match_id).sum()))
        distances, indices = self.tree.query(vector, k=count, workers=1)
        selected = [
            (int(i), float(d))
            for i, d in zip(
                np.atleast_1d(indices), np.atleast_1d(distances), strict=True
            )
            if self.match_ids[i] != match_id
        ][:k]
        rows = self.windows.iloc[[i for i, _ in selected]].to_dict("records")
        for row, (_, distance) in zip(rows, selected, strict=True):
            row["distance"] = distance
        return rows


NEGLIGIBLE_XG = 0.02
NEGLIGIBLE_POSSESSION = 0.01
NEGLIGIBLE_RESULT = 0.03
NEGLIGIBLE_CHANCE = 0.02


def counterfactual_response(
    match: dict,
    marker: dict,
    change: str,
    actual: list[dict],
    neighbours: list[dict],
    predictions: dict,
    model: dict,
    analog_goals: dict[str, list[dict]],
    factual: dict | None = None,
    lineup_change: dict | None = None,
    outlook: dict | None = None,
) -> dict:
    """Keep trained 15-minute totals separate from observed analog outcomes.

    `outlook` (goals.outlook) adds result and scoring-chance probabilities from
    the actual-goals model; they dominate the `negligible` decision.

    `factual` is the same model's forecast for the unchanged state: the honest
    comparison for `predictions`. Effects are changed minus factual medians.
    """
    focus = marker["team"]
    factual = factual or predictions

    def bands(forecast: dict) -> dict:
        return {
            side: {
                metric: {q: values[i] for q, values in forecast[target].items()}
                for metric, target in (
                    ("xg", "xg_for"),
                    ("possession", "possession_share"),
                )
            }
            for i, side in enumerate(("home", "away"))
        }

    modelled, unchanged = bands(predictions), bands(factual)
    effect = {
        side: {
            metric: round(
                modelled[side][metric]["p50"] - unchanged[side][metric]["p50"], 4
            )
            for metric in ("xg", "possession")
        }
        for side in ("home", "away")
    }

    def analog_band(side: str) -> dict:
        target = "outcome_xg_for" if side == focus else "outcome_xg_against"
        values = np.quantile([r[target] for r in neighbours], [0.1, 0.5, 0.9])
        return {f"p{q}": float(v) for q, v in zip((10, 50, 90), values, strict=True)}

    analogs = []
    for row in neighbours[:5]:
        future = [
            g
            for g in analog_goals[row["match_id"]]
            if row["elapsed_end_seconds"] <= g["t"] < row["elapsed_end_seconds"] + 900
        ]
        analogs.append(
            {
                "match_id": row["match_id"],
                **{k: row[k] for k in ("competition", "season", "home", "away")},
                "minute": int(row["minute"]),
                "score_state": f"{int(row['score_diff']):+d}",
                "similarity": 1 / (1 + row["distance"]),
                "next15": {
                    "xg_for": row["outcome_xg_for"],
                    "xg_against": row["outcome_xg_against"],
                    "goals_for": sum(g["team"] == row["team"] for g in future),
                    "goals_against": sum(g["team"] != row["team"] for g in future),
                },
            }
        )
    caps = {1: 45, 2: 90, 3: 105, 4: 120}
    shown, cap = marker["minute"] + 1, caps[marker["period"]]
    label = f"{cap}+{shown - cap}'" if shown > cap else f"{shown}'"
    return {
        "match_id": match["match_id"],
        "event_id": marker["event_id"],
        "change": change,
        "label": "Modelled hypothetical",
        "horizon_minutes": 15,
        "method": "trained_model",
        "model": model,
        "anchor": {
            "period": marker["period"],
            "minute": marker["minute"],
            "label": label,
        },
        "actual": actual[-1],
        "modelled": modelled,
        "factual": unchanged,
        "effect": effect,
        # Below this the change moves nothing a viewer would notice.
        "negligible": all(
            abs(effect[s]["xg"]) < NEGLIGIBLE_XG
            and abs(effect[s]["possession"]) < NEGLIGIBLE_POSSESSION
            for s in ("home", "away")
        )
        and (
            outlook is None
            or (
                max(
                    abs(
                        outlook["result"]["modelled"][k]
                        - outlook["result"]["factual"][k]
                    )
                    for k in ("home", "level", "away")
                )
                < NEGLIGIBLE_RESULT
                and max(
                    abs(
                        outlook["scoring_chance"]["modelled"][k]
                        - outlook["scoring_chance"]["factual"][k]
                    )
                    for k in ("home", "away")
                )
                < NEGLIGIBLE_CHANCE
            )
        ),
        **(outlook or {}),
        "lineup_change": lineup_change,
        "series": [
            {
                "offset_min": i,
                "actual": {s: row[s]["xg"] for s in ("home", "away")},
                "modelled": None,
            }
            for i, row in enumerate(actual)
        ],
        "analog_summary": {
            "n": len(neighbours),
            **{s: {"xg": analog_band(s)} for s in ("home", "away")},
        },
        "analogs": analogs,
        "n_analogs": len(neighbours),
        "caveat": CAVEAT,
    }
