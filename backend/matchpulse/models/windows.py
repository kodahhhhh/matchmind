"""Build retrospective windows with strict past/future boundaries and provenance.

Period-local clock seconds are concatenated using actual period end timestamps;
half-time breaks and shootouts are excluded. Five-minute history stays within
one period. Future horizons may cross half-time, counting playing time only.
Incomplete final horizons remain in the artifact but are excluded from fitting.
"""

import argparse
import hashlib
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from socceraction.spadl import play_left_to_right
from socceraction.vaep.formula import value
from socceraction.xthreat import ExpectedThreat

from matchpulse.models.common import (
    catalogue,
    data_dir,
    event_clock,
    event_seconds,
    raw_events,
)
from matchpulse.models.gamestate_model import BASE_FEATURES
from matchpulse.models.player_ratings import lineup_features
from matchpulse.models.xg import FEATURES as XG_FEATURES

_SHOTS: dict[int, pd.DataFrame] = {}
_MODELS: dict[str, lgb.Booster] = {}
_XT: ExpectedThreat | None = None


def initialize(fold: int | None) -> None:
    """Load each fold's upstream models once per worker, with one thread each."""
    global _SHOTS, _MODELS, _XT
    shots = pd.read_parquet(data_dir() / "processed/xg/shots.parquet")
    _SHOTS = dict(tuple(shots.groupby("game_id")))
    _MODELS = (
        {}
        if fold is None
        else {
            name: lgb.Booster(
                model_file=str(data_dir() / f"models/{name}_fold_{fold}.txt")
            )
            for name in ["xg", "vaep_scores", "vaep_concedes"]
        }
    )

    _XT = None
    if fold is not None:
        _XT = ExpectedThreat(l=12, w=8)
        _XT.xT = np.asarray(
            json.loads((data_dir() / "models/xt.json").read_text())["fold_grids"][fold]
        )


def build_match(match: dict[str, Any]) -> pd.DataFrame:
    native = match["native_id"]
    events = [e for e in raw_events(native) if e["period"] < 5]
    offsets, lengths = event_clock(events)
    full_time = sum(lengths.values())
    actions = pd.read_parquet(data_dir() / f"processed/vaep/{native}.parquet")
    if _MODELS:
        features = pd.read_parquet(
            data_dir() / f"processed/vaep_features/{native}.parquet"
        )
        columns = [
            c
            for c in features
            if c
            not in [
                "game_id",
                "action_id",
                "period_id",
                "label_scores",
                "label_concedes",
            ]
        ]
        for target in ["scores", "concedes"]:
            actions[f"p_{target}"] = _MODELS[f"vaep_{target}"].predict(
                features[columns].to_numpy(), num_threads=1
            )
        for _, ids in actions.groupby("period_id").groups.items():
            period = actions.loc[ids].reset_index(drop=True)
            values = value(period, period.p_scores, period.p_concedes)
            actions.loc[ids, "vaep_value"] = values.vaep_value.to_numpy()
    actions = play_left_to_right(
        actions[actions.period_id < 5].copy(), match["home"]["id"]
    )
    if _XT is None:
        xt = pd.read_parquet(data_dir() / f"processed/xt/{native}.parquet")
        actions["xt"] = actions.action_id.map(xt.set_index("action_id").xt)
    else:
        actions["xt"] = _XT.rate(actions)
    actions["elapsed"] = actions.time_seconds + actions.period_id.map(offsets)
    shots = _SHOTS[native].copy()
    if _MODELS:
        shots["xg"] = _MODELS["xg"].predict(shots[XG_FEATURES], num_threads=1)
    actions["xg"] = actions.original_event_id.map(
        shots.set_index("original_event_id").xg
    ).fillna(0)
    actions["is_shot"] = actions.type_name.str.startswith("shot")
    actions["is_pass"] = actions.type_name.isin(
        [
            "pass",
            "cross",
            "throw_in",
            "goalkick",
            "freekick_crossed",
            "freekick_short",
            "corner_crossed",
            "corner_short",
        ]
    )
    goals, subs, reds = [], [], []
    dismissed = set()
    active = {match["home"]["id"]: set(), match["away"]["id"]: set()}
    lineups = []  # (t, team, players on the pitch after the change)
    for event in events:
        team = event["team"]["id"]
        t = offsets[event["period"]] + event_seconds(event)
        kind = event["type"]["name"]
        if kind == "Shot" and event["shot"]["outcome"]["name"] == "Goal":
            goals.append((t, team))
        elif kind == "Own Goal Against":
            goals.append(
                (
                    t,
                    match["away"]["id"]
                    if team == match["home"]["id"]
                    else match["home"]["id"],
                )
            )
        if kind == "Starting XI":
            active[team] = {p["player"]["id"] for p in event["tactics"]["lineup"]}
            lineups.append((t, team, sorted(active[team])))
        if kind == "Substitution":
            subs.append((t, team))
            active[team].discard(event["player"]["id"])
            active[team].add(event["substitution"]["replacement"]["id"])
            lineups.append((t, team, sorted(active[team])))
        card = (
            event.get("bad_behaviour", {})
            .get("card", event.get("foul_committed", {}).get("card", {}))
            .get("name")
        )
        player = event.get("player", {}).get("id")
        if (
            card in ["Red Card", "Second Yellow"]
            and player not in dismissed
            and player in active[team]
        ):
            reds.append((t, team))
            dismissed.add(player)
            active[team].discard(player)
            lineups.append((t, team, sorted(active[team])))

    def on_pitch(team: int, end: float) -> list[int]:
        current: list[int] = []
        for t, side, players in lineups:
            if t < end and side == team:
                current = players
        return current

    rows = []
    nominal = {1: 0, 2: 45, 3: 90, 4: 105}
    for period, length in lengths.items():
        for end_local in np.arange(300, length + 0.001, 300):
            end = offsets[period] + end_local
            past = actions[
                (actions.elapsed >= end - 300)
                & (actions.elapsed < end)
                & (actions.period_id == period)
            ]
            future = actions[(actions.elapsed >= end) & (actions.elapsed < end + 900)]
            for side, other_side in [("home", "away"), ("away", "home")]:
                team, other = match[side]["id"], match[other_side]["id"]
                own, opp = past[past.team_id == team], past[past.team_id == other]
                future_own = future[future.team_id == team]
                future_opp = future[future.team_id == other]
                passes, future_passes = (
                    int(past.is_pass.sum()),
                    int(future.is_pass.sum()),
                )
                third = past.start_x > 70
                row = {
                    "match_id": match["match_id"],
                    "game_id": native,
                    "team": side,
                    "window_start": nominal[period] + end_local / 60 - 5,
                    "window_end": nominal[period] + end_local / 60,
                    "elapsed_end_seconds": end,
                    "horizon_seconds": min(900, max(0, full_time - end)),
                    "period": period,
                    "minute": nominal[period] + end_local / 60,
                    "score_diff": sum(t < end and g == team for t, g in goals)
                    - sum(t < end and g == other for t, g in goals),
                    "possession_share": float(own.is_pass.sum() / passes)
                    if passes
                    else 0.5,
                    "field_tilt": float(
                        ((past.team_id == team) & third).sum() / third.sum()
                    )
                    if third.sum()
                    else 0.5,
                    "xg_for": float(own.xg.sum()),
                    "xg_against": float(opp.xg.sum()),
                    "vaep_for": float(own.vaep_value.sum()),
                    "vaep_against": float(opp.vaep_value.sum()),
                    "xt_for_rate": float(own.xt.sum()) / 5,
                    "xt_against_rate": float(opp.xt.sum()) / 5,
                    "shots_for": int(own.is_shot.sum()),
                    "shots_against": int(opp.is_shot.sum()),
                    "minutes_since_sub": (
                        end
                        - max([t for t, g in subs if t < end and g == team], default=0)
                    )
                    / 60,
                    "minutes_since_opponent_sub": (
                        end
                        - max([t for t, g in subs if t < end and g == other], default=0)
                    )
                    / 60,
                    "players_for": 11 - sum(t < end and g == team for t, g in reds),
                    "players_against": 11
                    - sum(t < end and g == other for t, g in reds),
                    "on_pitch_for": on_pitch(team, end),
                    "on_pitch_against": on_pitch(other, end),
                    "is_home": int(side == "home"),
                    "international_tournament": int(
                        match["competition"]
                        in [
                            "FIFA World Cup",
                            "FIFA U20 World Cup",
                            "UEFA Euro",
                            "Copa America",
                            "African Cup of Nations",
                        ]
                    ),
                    "outcome_xg_for": float(future_own.xg.sum()),
                    "outcome_xg_against": float(future_opp.xg.sum()),
                    "outcome_possession_share": float(
                        future_own.is_pass.sum() / future_passes
                    )
                    if future_passes
                    else 0.5,
                    "future_passes": future_passes,
                    "competition": match["competition"],
                    "season": match["season"],
                    "home": match["home"]["name"],
                    "away": match["away"]["name"],
                    "match_date": match["match_date"],
                    "reconstructed": match["reconstructed"],
                }
                assert set(BASE_FEATURES).issubset(row)
                rows.append(row)
    return pd.DataFrame(rows)


def provenance(fold: int | None = None) -> str:
    """Fingerprint the upstream training runs and window/feature definitions."""
    digest = hashlib.sha256()
    paths = [data_dir() / f"models/{name}.json" for name in ["xg", "vaep", "xt"]]
    paths += [data_dir() / "catalogue/matches.json"]
    from pathlib import Path

    paths += [
        Path(__file__),
        Path(__file__).with_name("gamestate_model.py"),
        Path(__file__).with_name("common.py"),
        Path(__file__).with_name("player_ratings.py"),
    ]
    for path in paths:
        digest.update(path.read_bytes())
    digest.update(str(fold).encode())
    return digest.hexdigest()


def load_or_build(fold: int | None = None) -> pd.DataFrame:
    """Reuse only windows made from the current upstream artifacts and source."""
    suffix = "" if fold is None else f"_fold_{fold}"
    path = data_dir() / f"processed/gamestate_windows{suffix}.parquet"
    stamp = path.with_suffix(".provenance.json")
    if (
        path.exists()
        and stamp.exists()
        and json.loads(stamp.read_text())["sha256"] == provenance(fold)
    ):
        return pd.read_parquet(path)
    return build(fold)


def build(fold: int | None = None) -> pd.DataFrame:
    with ProcessPoolExecutor(
        max_workers=16,
        initializer=initialize,
        initargs=(fold,),
        mp_context=multiprocessing.get_context("spawn"),
    ) as pool:
        frames = []
        for i, frame in enumerate(pool.map(build_match, catalogue()), 1):
            frames.append(frame)
            if i % 500 == 0:
                print("Windows", fold, i, flush=True)
    result = pd.concat(frames, ignore_index=True)
    # Own match always excluded; fold builds also exclude the held-out fold.
    result = result.join(lineup_features(result, fold))
    suffix = "" if fold is None else f"_fold_{fold}"
    result.to_parquet(
        data_dir() / f"processed/gamestate_windows{suffix}.parquet", index=False
    )
    stamp = data_dir() / f"processed/gamestate_windows{suffix}.provenance.json"
    stamp.write_text(json.dumps({"sha256": provenance(fold), "fold": fold}))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fold", type=int)
    args = parser.parse_args()
    build(args.fold)


if __name__ == "__main__":
    main()
