"""Quantile forecasts of the next 15 playing minutes, in team perspective.

featurize accepts flat window rows or rows with a nested `features` dictionary.
FEATURES is the exact ordered inference contract. Past-window sums cover five
minutes; possession is pass-count share (all pass actions),
field tilt is the share of actions starting in the attacking third. Both are
fractions. xT rates are successful-move value per minute. Substitution ages
and minute are minutes; xG/VAEP are window sums.

predict returns target -> {p10, p50, p90}, each a list aligned with input rows.
All forecasts/counterfactuals must be labelled MODELLED. To form a hypothetical,
copy the feature row and change just the intervention: remove_goal subtracts
one from score_diff for the scoring side (adds one for its opponent); no_sub
resets minutes_since_sub to its pre-substitution age, or elapsed match minutes
if no prior substitution, and swaps the incoming player's rating back to the
outgoing player's in lineup_vaep; remove_red_card restores the affected players
count (up to 11) and the dismissed player's rating. Do not blindly restore
both teams if only one card is removed. Re-predict the copy. This is an
observational sensitivity calculation, NOT a
causal estimate: goals, substitutions and dismissals are not randomized.
"""

from functools import lru_cache
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from matchmind.models.common import data_dir

BASE_FEATURES = [
    "minute",
    "period",
    "score_diff",
    "possession_share",
    "field_tilt",
    "xg_for",
    "xg_against",
    "vaep_for",
    "vaep_against",
    "xt_for_rate",
    "xt_against_rate",
    "shots_for",
    "shots_against",
    "minutes_since_sub",
    "minutes_since_opponent_sub",
    "players_for",
    "players_against",
    "is_home",
    "international_tournament",
]
# Sum of on-pitch players' leave-one-match-out VAEP per 90 (player_ratings).
LINEUP_FEATURES = ["lineup_vaep_for", "lineup_vaep_against"]
FEATURES = BASE_FEATURES + LINEUP_FEATURES
TARGETS = ["xg_for", "xg_against", "possession_share"]
QUANTILES = [0.1, 0.5, 0.9]


def featurize(window_rows: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    """Select exact FEATURES, reject missing/nonfinite columns and preserve order."""
    frame = pd.DataFrame(window_rows).copy()
    if "features" in frame:
        frame = pd.DataFrame(frame.features.tolist(), index=frame.index)
    missing = set(FEATURES) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing game-state features: {sorted(missing)}")
    result = frame[FEATURES].astype(float)
    if not np.isfinite(result.to_numpy()).all():
        raise ValueError("Game-state features must be finite")
    return result


@lru_cache(maxsize=9)
def _model(target: str, quantile: int) -> lgb.Booster:
    return lgb.Booster(
        model_file=str(data_dir() / f"models/gamestate_{target}_p{quantile}.txt")
    )


def bound_predictions(values: np.ndarray, target: str) -> np.ndarray:
    """Rearrange crossing quantiles and enforce each target's physical support."""
    return np.sort(
        np.clip(values, 0, 1 if target == "possession_share" else np.inf), axis=1
    )


@lru_cache(maxsize=1)
def _calibration() -> dict[str, list[float]]:
    """Per-target outer-quantile scale factors fitted on out-of-fold forecasts."""
    import json

    report = json.loads((data_dir() / "models/gamestate.json").read_text())
    return report.get("calibration", {}).get("factors", {})


def calibrate(values: np.ndarray, target: str, factors: list[float]) -> np.ndarray:
    """Stretch p10/p90 around p50 by fitted factors (1.0 = unchanged)."""
    out = values.copy()
    out[:, 0] = values[:, 1] - factors[0] * (values[:, 1] - values[:, 0])
    out[:, 2] = values[:, 1] + factors[1] * (values[:, 2] - values[:, 1])
    return bound_predictions(out, target)


def predict(features: pd.DataFrame) -> dict[str, dict[str, list[float]]]:
    frame = featurize(features)
    result = {}
    for target in TARGETS:
        values = bound_predictions(
            np.column_stack(
                [_model(target, q).predict(frame, num_threads=1) for q in [10, 50, 90]]
            ),
            target,
        )
        if target in _calibration():
            values = calibrate(values, target, _calibration()[target])
        result[target] = {
            f"p{q}": values[:, i].tolist() for i, q in enumerate([10, 50, 90])
        }
    return result


PASS_TYPES = {
    "pass",
    "cross",
    "throw_in",
    "goalkick",
    "freekick_crossed",
    "freekick_short",
    "corner_crossed",
    "corner_short",
}
INTERNATIONAL = {
    "FIFA World Cup",
    "FIFA U20 World Cup",
    "UEFA Euro",
    "Copa America",
    "African Cup of Nations",
}


def match_context(raw: list[dict], match: dict) -> dict:
    """Training-clock anchors and score/sub/on-pitch dismissal history.

    Preserve source ordering to avoid leaking a later event at the same timestamp.
    Bench cards and repeated dismissals do not change player counts.
    """
    from matchmind.models.common import event_clock, event_seconds

    events = [e for e in raw if e["period"] < 5]
    offsets, lengths = event_clock(events)
    sides = {match[s]["id"]: s for s in ("home", "away")}
    active = {s: set() for s in sides.values()}
    dismissed = set()
    anchors, markers = {}, []
    starting: dict[str, list[int]] = {s: [] for s in sides.values()}
    for event in events:
        side = sides[event["team"]["id"]]
        kind = event["type"]["name"]
        player = event.get("player", {}).get("id")
        anchor = {
            "event_id": f"{match['match_id']}:{event['index']}",
            "index": event["index"],
            "period": event["period"],
            "minute": event["minute"],
            "team": side,
            "local_seconds": event_seconds(event),
            "t": offsets[event["period"]] + event_seconds(event),
        }
        anchors[anchor["event_id"]] = anchor
        if kind == "Shot" and event["shot"]["outcome"]["name"] == "Goal":
            markers.append({**anchor, "type": "goal"})
        elif kind == "Own Goal Against":
            markers.append(
                {**anchor, "type": "goal", "team": "away" if side == "home" else "home"}
            )
        if kind == "Starting XI":
            active[side] = {p["player"]["id"] for p in event["tactics"]["lineup"]}
            starting[side] = sorted(active[side])
        if kind == "Substitution":
            markers.append(
                {
                    **anchor,
                    "type": "sub",
                    "player_off": player,
                    "player_on": event["substitution"]["replacement"]["id"],
                }
            )
            active[side].discard(player)
            active[side].add(event["substitution"]["replacement"]["id"])
        card = (
            event.get("bad_behaviour", {})
            .get("card", event.get("foul_committed", {}).get("card", {}))
            .get("name")
        )
        if (
            card in ("Red Card", "Second Yellow")
            and player not in dismissed
            and player in active[side]
        ):
            markers.append({**anchor, "type": "red", "player": player})
            dismissed.add(player)
            active[side].discard(player)
    return {
        "anchors": anchors,
        "markers": markers,
        "starting": starting,
        "offsets": offsets,
        "lengths": lengths,
    }


def on_pitch(context: dict, side: str, markers: list[dict]) -> list[int]:
    """Players on the pitch for `side` after replaying the given markers."""
    players = set(context.get("starting", {}).get(side, []))
    for m in markers:
        if m["team"] != side:
            continue
        if m["type"] == "sub":
            players.discard(m["player_off"])
            players.add(m["player_on"])
        elif m["type"] == "red":
            players.discard(m["player"])
    return sorted(players)


def prepare_actions(
    actions: pd.DataFrame,
    xt: pd.DataFrame,
    shots: pd.DataFrame,
    raw: list[dict],
    match: dict,
    context: dict,
) -> pd.DataFrame:
    """Join OOF SPADL values exactly as windows.build_match does; retain dribbles."""
    result = actions[actions.period_id < 5].copy()
    away = result.team_id != match["home"]["id"]
    result.loc[away, "start_x"] = 105 - result.loc[away, "start_x"]
    result["xt"] = result.action_id.map(xt.set_index("action_id").xt)
    result["xg"] = result.original_event_id.map(
        shots.set_index("original_event_id").xg
    ).fillna(0)
    result["elapsed"] = result.time_seconds + result.period_id.map(context["offsets"])
    result["is_shot"] = result.type_name.str.startswith("shot")
    result["is_pass"] = result.type_name.isin(PASS_TYPES)
    indices = {e["id"]: e["index"] for e in raw}
    # Synthetic dribbles lie between actions. Timestamp is sufficient except ties;
    # at a tied timestamp, use the next real action's position in the source.
    result["source_index"] = (
        result.original_event_id.map(indices).bfill().fillna(float("inf"))
    )
    return result


def player_ratings(context: dict, match: dict) -> dict[int, float]:
    """Leave-this-match-out VAEP per 90 for everyone who appears in the lineups."""
    from matchmind.models.player_ratings import ratings_lomo

    ids = {p for side in context["starting"].values() for p in side}
    for m in context["markers"]:
        ids.update(m[k] for k in ("player_off", "player_on", "player") if k in m)
    return ratings_lomo(sorted(ids), match["native_id"])


def anchor_features(
    actions: pd.DataFrame,
    context: dict,
    anchor: dict,
    match: dict,
    *,
    include_anchor: bool = True,
) -> pd.DataFrame:
    """Home then away FEATURES; five period-local minutes, including the anchor.

    include_anchor=False reproduces saved [end-300, end) training windows.
    Histories use SPADL sums, all pass types and acting-frame START-x field tilt.
    """
    end = anchor["t"]
    if include_anchor:
        before = (actions.elapsed < end) | (
            (actions.elapsed == end) & (actions.source_index <= anchor["index"])
        )
        markers = [
            m
            for m in context["markers"]
            if (m["t"], m["index"]) <= (end, anchor["index"])
        ]
    else:
        before = actions.elapsed < end
        markers = [m for m in context["markers"] if m["t"] < end]
    past = actions[
        (actions.elapsed >= end - 300)
        & before
        & (actions.period_id == anchor["period"])
    ]
    passes = int(past.is_pass.sum())
    third = past.start_x > 70
    ratings = player_ratings(context, match) if "starting" in context else {}
    rows = []
    for side, opposite in (("home", "away"), ("away", "home")):
        own = past[past.team_id == match[side]["id"]]
        opp = past[past.team_id == match[opposite]["id"]]
        row = {
            "minute": {1: 0, 2: 45, 3: 90, 4: 105}[anchor["period"]]
            + anchor["local_seconds"] / 60,
            "period": anchor["period"],
            "score_diff": sum(
                m["type"] == "goal" and m["team"] == side for m in markers
            )
            - sum(m["type"] == "goal" and m["team"] == opposite for m in markers),
            "possession_share": float(own.is_pass.sum() / passes) if passes else 0.5,
            "field_tilt": float(
                ((past.team_id == match[side]["id"]) & third).sum() / third.sum()
            )
            if third.any()
            else 0.5,
            "minutes_since_sub": (
                end
                - max(
                    (
                        m["t"]
                        for m in markers
                        if m["type"] == "sub" and m["team"] == side
                    ),
                    default=0,
                )
            )
            / 60,
            "minutes_since_opponent_sub": (
                end
                - max(
                    (
                        m["t"]
                        for m in markers
                        if m["type"] == "sub" and m["team"] == opposite
                    ),
                    default=0,
                )
            )
            / 60,
            "players_for": 11
            - sum(m["type"] == "red" and m["team"] == side for m in markers),
            "players_against": 11
            - sum(m["type"] == "red" and m["team"] == opposite for m in markers),
            "is_home": int(side == "home"),
            "international_tournament": int(match["competition"] in INTERNATIONAL),
        }
        for tag, team in (("for", side), ("against", opposite)):
            row[f"lineup_vaep_{tag}"] = sum(
                ratings[p] for p in on_pitch(context, team, markers)
            )
        for frame, tag in ((own, "for"), (opp, "against")):
            row[f"xg_{tag}"] = float(frame.xg.sum())
            row[f"vaep_{tag}"] = float(frame.vaep_value.sum())
            row[f"xt_{tag}_rate"] = float(frame.xt.sum()) / 5
            row[f"shots_{tag}"] = int(frame.is_shot.sum())
        rows.append(row)
    return featurize(rows)


def intervene(
    factual: pd.DataFrame,
    anchor: dict,
    context: dict,
    change: str,
    ratings: dict[int, float] | None = None,
) -> pd.DataFrame:
    """Edit both perspectives of a copy; preserve observed pre-intervention history."""
    result = featurize(factual)
    own, other = (0, 1) if anchor["team"] == "home" else (1, 0)
    if change == "remove_goal":
        result.loc[own, "score_diff"] -= 1
        result.loc[other, "score_diff"] += 1
    elif change == "no_sub":
        previous = [
            m["t"]
            for m in context["markers"]
            if m["type"] == "sub"
            and m["team"] == anchor["team"]
            and (m["t"], m["index"]) < (anchor["t"], anchor["index"])
        ]
        age = (anchor["t"] - max(previous, default=0)) / 60
        result.loc[own, "minutes_since_sub"] = age
        result.loc[other, "minutes_since_opponent_sub"] = age
        sub = next(
            (
                m
                for m in context["markers"]
                if m["type"] == "sub" and m.get("event_id") == anchor["event_id"]
            ),
            None,
        )
        if sub is not None and ratings is not None:
            swing = ratings[sub["player_off"]] - ratings[sub["player_on"]]
            result.loc[own, "lineup_vaep_for"] += swing
            result.loc[other, "lineup_vaep_against"] += swing
    elif change == "remove_red_card":
        red = next(
            (
                m
                for m in context["markers"]
                if m["type"] == "red" and m.get("event_id") == anchor["event_id"]
            ),
            None,
        )
        if red is not None:
            result.loc[own, "players_for"] = min(11, result.loc[own, "players_for"] + 1)
            result.loc[other, "players_against"] = min(
                11, result.loc[other, "players_against"] + 1
            )
            if ratings is not None:
                result.loc[own, "lineup_vaep_for"] += ratings[red["player"]]
                result.loc[other, "lineup_vaep_against"] += ratings[red["player"]]
    else:
        raise ValueError(f"Unsupported intervention: {change}")
    return result
