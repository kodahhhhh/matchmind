"""Pass-instead-of-shot alternatives: a 360 pass-completion model plus follow-up value.

Training: open-play passes from matches with StatsBomb 360 freeze frames. The
label is completion (offside and intercepted passes fail). Features describe the
pass geometry and the defenders around the lane and target, all available before
the pass; pass type, height and body part are deliberately excluded because a
hypothetical pass has none.

Inference: at a shot, each teammate in the shot freeze frame is a pass target.
option value = P(complete) x max(xG if the receiver shot from there, xT of the
receiver's zone). The xG uses our shot model (the fold that never saw this
match, as for every xG in the app) with the same defenders and keeper,
assuming a clean first-time strike; xT is the corpus-average value of holding
the ball in that zone. Both are probabilities that the possession ends in a goal,
so they compare with the actual shot's xG. This is a modelled hypothetical, not
what would have happened: defenders would react and receptions can fail.

Coordinates are SPADL metres in the acting team's attacking frame (left to
right); callers orient them for the API.
"""

import json
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from matchpulse.models.common import (
    catalogue,
    data_dir,
    fold_map,
    raw_events,
    save_json,
    timestamp,
)

SET_PIECES = {"Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"}
IGNORED_OUTCOMES = {"Injury Clearance", "Unknown"}
GEOMETRY = ["start_x", "start_y", "end_x", "end_y", "distance", "dx", "angle"]
FEATURES = GEOMETRY + [
    "lane_opponents_1",
    "lane_opponents_3",
    "nearest_opponent_end",
    "opponents_near_end",
    "nearest_opponent_start",
    "beyond_offside_line",
    "under_pressure",
    "visible_opponents",
]
PARAMS = dict(
    n_estimators=300,
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=100,
    reg_lambda=5,
    n_jobs=16,
    verbosity=-1,
    random_state=2026,
)


def spadl_xy(location: list[float]) -> tuple[float, float]:
    """StatsBomb 120x80 top-left to SPADL 105x68 bottom-left, same attacking frame."""
    return location[0] * 105 / 120, (80 - location[1]) * 68 / 80


def pass_features(
    start: tuple[float, float],
    end: tuple[float, float],
    opponents: list[tuple[float, float]],
    under_pressure: bool,
) -> dict[str, float]:
    """Geometry and defenders for one (real or hypothetical) pass."""
    (sx, sy), (ex, ey) = start, end
    vx, vy = ex - sx, ey - sy
    length = float(np.hypot(vx, vy))
    row = {
        "start_x": sx,
        "start_y": sy,
        "end_x": ex,
        "end_y": ey,
        "distance": length,
        "dx": vx,
        "angle": float(abs(np.arctan2(vy, vx))),
        "lane_opponents_1": 0.0,
        "lane_opponents_3": 0.0,
        "opponents_near_end": 0.0,
        "under_pressure": float(under_pressure),
        "visible_opponents": float(len(opponents)),
    }
    near_end, near_start = [], []
    for ox, oy in opponents:
        near_end.append(float(np.hypot(ox - ex, oy - ey)))
        near_start.append(float(np.hypot(ox - sx, oy - sy)))
        if length > 1e-6:
            along = ((ox - sx) * vx + (oy - sy) * vy) / length
            if 0 < along < length:
                perpendicular = abs((ox - sx) * vy - (oy - sy) * vx) / length
                row["lane_opponents_1"] += perpendicular <= 1.5
                row["lane_opponents_3"] += perpendicular <= 3
        row["opponents_near_end"] += near_end[-1] <= 5
    row["nearest_opponent_end"] = min(near_end, default=30.0)
    row["nearest_opponent_start"] = min(near_start, default=30.0)
    # Second-last visible defender (the keeper usually being last) sets the line.
    xs = sorted((ox for ox, _ in opponents), reverse=True)
    line = max(xs[1] if len(xs) > 1 else 52.5, sx, 52.5)
    row["beyond_offside_line"] = ex - line
    return row


def extract_match(match: dict[str, Any]) -> list[dict[str, Any]]:
    """Open-play passes with a 360 frame; label = completed."""
    native = match["native_id"]
    path = data_dir() / f"raw/statsbomb/data/three-sixty/{native}.json"
    if not path.exists():
        return []
    frames = {f["event_uuid"]: f for f in json.loads(path.read_text())}
    rows = []
    for event in raw_events(native):
        if event["type"]["name"] != "Pass" or event["id"] not in frames:
            continue
        detail = event["pass"]
        if detail.get("type", {}).get("name") in SET_PIECES:
            continue
        outcome = detail.get("outcome", {}).get("name")
        if outcome in IGNORED_OUTCOMES:
            continue
        opponents = [
            spadl_xy(p["location"])
            for p in frames[event["id"]]["freeze_frame"]
            if not p["teammate"]
        ]
        rows.append(
            {
                "game_id": native,
                "complete": int(outcome is None),
                **pass_features(
                    spadl_xy(event["location"]),
                    spadl_xy(detail["end_location"]),
                    opponents,
                    event.get("under_pressure", False),
                ),
            }
        )
    return rows


def train() -> None:
    with ProcessPoolExecutor(max_workers=16) as pool:
        rows = [r for group in pool.map(extract_match, catalogue()) for r in group]
    data = pd.DataFrame(rows)
    folds = data.game_id.map(fold_map()).to_numpy()
    y = data.complete.to_numpy()
    oof = {"model": np.zeros(len(data)), "geometry_only": np.zeros(len(data))}
    for fold in range(5):
        test = folds == fold
        for name, columns in (("model", FEATURES), ("geometry_only", GEOMETRY)):
            model = lgb.LGBMClassifier(**PARAMS).fit(data.loc[~test, columns], y[~test])
            oof[name][test] = model.predict_proba(data.loc[test, columns])[:, 1]

    def score(p: np.ndarray) -> dict[str, float]:
        return {
            "auc": float(roc_auc_score(y, p)),
            "brier": float(brier_score_loss(y, p)),
            "log_loss": float(log_loss(y, p)),
        }

    deciles = pd.qcut(oof["model"], 10, labels=False, duplicates="drop")
    calibration = [
        {
            "decile": int(d),
            "n": int((deciles == d).sum()),
            "predicted": float(oof["model"][deciles == d].mean()),
            "observed": float(y[deciles == d].mean()),
        }
        for d in sorted(set(deciles))
    ]
    model = lgb.LGBMClassifier(**PARAMS).fit(data[FEATURES], y)
    model.booster_.save_model(str(data_dir() / "models/pass_options.txt"))
    save_json(
        "pass_options.json",
        {
            "training_date": timestamp(),
            "n_matches": int(data.game_id.nunique()),
            "n_passes": len(data),
            "completion_rate": float(y.mean()),
            "features": FEATURES,
            "params": PARAMS,
            "validation": (
                "5 grouped match folds over open-play passes with StatsBomb 360 "
                "freeze frames; geometry-only model is the no-defenders baseline"
            ),
            "metrics": {
                "model": score(oof["model"]),
                "geometry_only": score(oof["geometry_only"]),
                "calibration_deciles": calibration,
            },
        },
    )
    print(score(oof["model"]), score(oof["geometry_only"]), flush=True)


@lru_cache(maxsize=1)
def _completion_model() -> lgb.Booster:
    return lgb.Booster(model_file=str(data_dir() / "models/pass_options.txt"))


@lru_cache(maxsize=5)
def _xg_model(fold: int) -> lgb.Booster:
    """The xG fold model that never saw this match: it produced the app's xG."""
    return lgb.Booster(model_file=str(data_dir() / f"models/xg_fold_{fold}.txt"))


@lru_cache(maxsize=1)
def model_report() -> dict:
    return json.loads((data_dir() / "models/pass_options.json").read_text())


@lru_cache(maxsize=1)
def _xt_grid() -> np.ndarray:
    return np.asarray(json.loads((data_dir() / "models/xt.json").read_text())["grid"])


def xt_value(x: float, y: float) -> float:
    """socceraction cell convention: grid row 0 is the top (high y) of the pitch."""
    grid = _xt_grid()
    rows, cols = grid.shape
    i = min(max(int(x / 105 * cols), 0), cols - 1)
    j = min(max(int(y / 68 * rows), 0), rows - 1)
    return float(grid[rows - 1 - j, i])


def shot_xg(
    event: dict, score_diff: int, fold: int, related_pass: dict | None = None
) -> float:
    from matchpulse.models.xg import FEATURES as XG_FEATURES
    from matchpulse.models.xg import shot_features

    row = {**shot_features(event, related_pass), "score_diff": score_diff}
    frame = pd.DataFrame([row])[XG_FEATURES].astype(float)
    return float(_xg_model(fold).predict(frame, num_threads=1)[0])


def alternatives(
    shot: dict, score_diff: int, native_id: int, related_pass: dict | None = None
) -> dict[str, Any]:
    """Score every teammate in a shot's freeze frame as a pass target.

    `shot` is the raw StatsBomb shot event; `related_pass` its key pass.
    Returns the shot's own xG and the options sorted by modelled value, in the
    shooter's attacking frame.
    """
    frame = shot["shot"].get("freeze_frame", [])
    start = spadl_xy(shot["location"])
    opponents = [spadl_xy(p["location"]) for p in frame if not p["teammate"]]
    teammates = [p for p in frame if p["teammate"]]
    fold = fold_map()[native_id]
    actual = shot_xg(shot, score_diff, fold, related_pass)
    if not teammates:
        return {"shot_xg": actual, "options": []}
    features = pd.DataFrame(
        [
            pass_features(
                start,
                spadl_xy(p["location"]),
                opponents,
                shot.get("under_pressure", False),
            )
            for p in teammates
        ]
    )[FEATURES].astype(float)
    completion = _completion_model().predict(features, num_threads=1)
    options = []
    for p, chance in zip(teammates, completion, strict=True):
        x, y = spadl_xy(p["location"])
        # The receiver takes the shot; the shooter becomes a teammate in the frame.
        others = [q for q in frame if q is not p] + [
            {"location": shot["location"], "teammate": True}
        ]
        hypothetical = {
            **shot,
            "location": p["location"],
            "under_pressure": False,
            "shot": {
                "type": {"name": "Open Play"},
                "body_part": {"name": "Right Foot"},
                "technique": {"name": "Normal"},
                "first_time": True,
                "freeze_frame": others,
            },
            "play_pattern": {"name": "Regular Play"},
        }
        receiver_xg = shot_xg(hypothetical, score_diff, fold)
        threat = xt_value(x, y)
        options.append(
            {
                "player_id": p.get("player", {}).get("id"),
                "player": p.get("player", {}).get("name"),
                "x": round(x, 2),
                "y": round(y, 2),
                "p_complete": float(chance),
                "xg_if_shot": receiver_xg,
                "xt": threat,
                "value": float(chance) * max(receiver_xg, threat),
            }
        )
    options.sort(key=lambda o: -o["value"])
    return {"shot_xg": actual, "options": options}


if __name__ == "__main__":
    train()
