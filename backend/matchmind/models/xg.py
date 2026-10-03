"""Pre-shot xG with match-held-out predictions and local freeze-frame geometry."""

from concurrent.futures import ProcessPoolExecutor
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from matchmind.models.common import (
    catalogue,
    data_dir,
    fold_map,
    raw_events,
    save_json,
    timestamp,
)

CATEGORIES = {
    "body_part": ["Left Foot", "Right Foot", "Head", "Other"],
    "shot_type": ["Open Play", "Free Kick", "Corner", "Penalty", "Other"],
    "technique": [
        "Normal",
        "Volley",
        "Half Volley",
        "Lob",
        "Overhead Kick",
        "Backheel",
        "Diving Header",
        "Other",
    ],
}
FEATURES = [
    "distance",
    "angle",
    "x",
    "y_offset",
    "body_part",
    "shot_type",
    "technique",
    "first_time",
    "under_pressure",
    "through_ball",
    "cross",
    "cut_back",
    "set_piece",
    "freeze_frame_present",
    "opponents_in_cone",
    "keeper_present",
    "keeper_goal_distance",
    "keeper_shot_line_distance",
    "score_diff",
    "minute",
]


def shot_features(
    event: dict[str, Any], related_pass: dict[str, Any] | None = None
) -> dict[str, float]:
    """Use only information available before the shot; never outcome/end location."""
    shot = event["shot"]
    x, y = event["location"][:2]
    x, y = x * 105 / 120, (80 - y) * 68 / 80
    dx, dy = 105 - x, 34 - y
    angle = np.arctan2(7.32 * max(dx, 0), dx * dx + dy * dy - (7.32 / 2) ** 2)
    row = {
        "x": x,
        "y_offset": abs(dy),
        "distance": np.hypot(dx, dy),
        "angle": angle,
        "first_time": float(shot.get("first_time", False)),
        "under_pressure": float(event.get("under_pressure", False)),
        "minute": event["minute"],
    }
    for key, values in CATEGORIES.items():
        name = shot.get(key, {}).get("name", "Other")
        if key == "shot_type":
            name = shot.get("type", {}).get("name", "Open Play")
            if (
                name == "Open Play"
                and event.get("play_pattern", {}).get("name") == "From Corner"
            ):
                name = "Corner"
        row[key] = float(
            values.index(name) if name in values else values.index("Other")
        )
    assist = (related_pass or {}).get("pass", {})
    row.update(
        {
            key: float(assist.get(key, False))
            for key in ["through_ball", "cross", "cut_back"]
        }
    )
    row["set_piece"] = float(
        assist.get("type", {}).get("name") in ["Free Kick", "Corner", "Throw-in"]
        or row["shot_type"] in [1, 2, 3]
    )
    frame = shot.get("freeze_frame", [])
    row.update(
        freeze_frame_present=float(bool(frame)),
        opponents_in_cone=0.0,
        keeper_present=0.0,
        keeper_goal_distance=np.nan,
        keeper_shot_line_distance=np.nan,
    )
    for player in frame:
        if player["teammate"]:
            continue
        px, py = player["location"][:2]
        px, py = px * 105 / 120, (80 - py) * 68 / 80
        if dx > 0 and x <= px <= 105:
            ratio = (px - x) / dx
            if y + ratio * (34 - 3.66 - y) <= py <= y + ratio * (34 + 3.66 - y):
                row["opponents_in_cone"] += 1
        if player.get("position", {}).get("name") == "Goalkeeper":
            row["keeper_present"] = 1.0
            row["keeper_goal_distance"] = abs(105 - px)
            row["keeper_shot_line_distance"] = abs(dx * (py - y) - dy * (px - x)) / max(
                np.hypot(dx, dy), 1e-8
            )
    return row


def extract_match(match: dict[str, Any]) -> list[dict[str, Any]]:
    events = raw_events(match["native_id"])
    by_id = {e["id"]: e for e in events}
    score = {match["home"]["id"]: 0, match["away"]["id"]: 0}
    rows = []
    for event in events:
        team = event["team"]["id"]
        other = (
            match["away"]["id"] if team == match["home"]["id"] else match["home"]["id"]
        )
        if event["type"]["name"] == "Shot":
            shot = event["shot"]
            assist = by_id.get(shot.get("key_pass_id"))
            row = shot_features(event, assist)
            row.update(
                score_diff=score[team] - score[other],
                game_id=match["native_id"],
                original_event_id=event["id"],
                goal=int(shot["outcome"]["name"] == "Goal"),
                sb_xg=shot.get("statsbomb_xg"),
                period=event["period"],
            )
            rows.append(row)
            if event["period"] < 5:
                score[team] += row["goal"]
        elif event["type"]["name"] == "Own Goal Against":
            score[other] += 1
    return rows


def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    p = np.clip(p, 1e-7, 1 - 1e-7)
    bins = pd.DataFrame({"prediction": p, "goal": y})
    bins["decile"] = pd.qcut(bins.prediction.rank(method="first"), 10, labels=False)
    table = (
        bins.groupby("decile")
        .agg(
            n=("goal", "size"),
            predicted=("prediction", "mean"),
            observed=("goal", "mean"),
        )
        .reset_index()
    )
    return {
        "log_loss": float(log_loss(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "auc": float(roc_auc_score(y, p)),
        "total_xg": float(p.sum()),
        "goals": int(y.sum()),
        "calibration_deciles": table.to_dict("records"),
    }


def main() -> None:
    with ProcessPoolExecutor(max_workers=16) as pool:
        rows = [row for group in pool.map(extract_match, catalogue()) for row in group]
    shots = pd.DataFrame(rows)
    shots["fold"] = shots.game_id.map(fold_map())
    x, y = shots[FEATURES], shots.goal
    eligible = shots.period < 5
    predictions = np.zeros(len(shots))
    params = dict(
        n_estimators=350,
        learning_rate=0.035,
        num_leaves=15,
        min_child_samples=150,
        reg_lambda=5,
        n_jobs=16,
        verbosity=-1,
        random_state=2026,
    )
    folds = []
    for fold in range(5):
        test = shots.fold == fold
        model = lgb.LGBMClassifier(**params).fit(
            x[~test & eligible], y[~test & eligible]
        )
        predictions[test] = model.predict_proba(x[test])[:, 1]
        folds.append(
            metrics(y[test & eligible].to_numpy(), predictions[test & eligible])
        )
        model.booster_.save_model(str(data_dir() / f"models/xg_fold_{fold}.txt"))
        print("xG fold", fold, folds[-1]["log_loss"], flush=True)
    shots["xg"] = predictions
    path = data_dir() / "processed/xg/shots.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    shots.to_parquet(path, index=False)
    model = lgb.LGBMClassifier(**params).fit(x[eligible], y[eligible])
    (data_dir() / "models").mkdir(exist_ok=True)
    model.booster_.save_model(str(data_dir() / "models/xg.txt"))
    benchmark = shots.sb_xg.notna() & eligible
    report = {
        "training_date": timestamp(),
        "n_shots": int(eligible.sum()),
        "n_shootout_predictions": int((~eligible).sum()),
        "n_matches": int(shots.game_id.nunique()),
        "features": FEATURES,
        "categories": CATEGORIES,
        "params": params,
        "validation": (
            "5 grouped match folds; uncalibrated probabilities; "
            "shootouts predicted but excluded from training/evaluation"
        ),
        "metrics": metrics(y[eligible].to_numpy(), predictions[eligible]),
        "benchmark_n": int(benchmark.sum()),
        "same_shots_ours": metrics(y[benchmark].to_numpy(), predictions[benchmark]),
        "statsbomb": metrics(
            y[benchmark].to_numpy(), shots.loc[benchmark, "sb_xg"].to_numpy()
        ),
        "fold_metrics": folds,
    }
    save_json("xg.json", report)
    print(
        {
            k: v
            for k, v in report.items()
            if k in ["n_shots", "n_matches", "metrics", "statsbomb"]
        },
        flush=True,
    )


if __name__ == "__main__":
    main()
