"""Pre-2015 base features, chronological result training and held-out calibration."""

import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from socceraction.vaep.formula import value

from matchmind.backtest.common import catalogue, output, root, save
from matchmind.backtest.statistics import scores
from matchmind.models.xg import FEATURES as XG_FEATURES

FEATURES = [
    "minute",
    "period",
    "score_home",
    "score_away",
    "score_diff",
    "red_home",
    "red_away",
    "xg_home",
    "xg_away",
    "recent_xg_home",
    "recent_xg_away",
    "recent_vaep_home",
    "recent_vaep_away",
    "international",
]
BASELINE = ["minute", "period", "score_home", "score_away", "score_diff"]
EXCLUDED = {(43, "2022"), (55, "2024"), (223, "2024")}


def is_test(match: dict) -> bool:
    return (match["competition"], match["season"]) in {
        ("FIFA World Cup", "2022"),
        ("UEFA Euro", "2024"),
        ("Copa America", "2024"),
    }


def split(match: dict) -> str:
    if is_test(match):
        return "backtest"
    date = match["match_date"]
    if date and date < "2015-08-01":
        return "upstream"
    if not date:
        return (
            "train"
            if match["competition_id"] == 9 and match["season"] == "2015/2016"
            else "excluded"
        )
    if date < "2018-01-01":
        return "train"
    if date < "2020-01-01":
        return "calibration"
    if date < "2022-11-01":
        return "validation"
    return "excluded"


def train_base() -> None:
    """Fit VAEP only on the historical upstream partition, never test tournaments."""
    destination = root() / "models/backtest_vaep.joblib"
    if destination.exists():
        return
    matches = [m for m in catalogue() if m["training"] and split(m) == "upstream"]
    excluded = {"game_id", "action_id", "period_id", "label_scores", "label_concedes"}
    frames = []
    for m in matches:
        frame = pd.read_parquet(
            root() / f"processed/vaep_features/{m['native_id']}.parquet"
        )
        frames.append(frame[frame.period_id < 3])
    data = pd.concat(frames, ignore_index=True)
    features = [c for c in data if c not in excluded]
    models = {}
    for target in ("scores", "concedes"):
        model = lgb.LGBMClassifier(
            n_estimators=100,
            num_leaves=15,
            learning_rate=0.07,
            min_child_samples=250,
            max_bin=63,
            reg_lambda=5,
            n_jobs=4,
            verbosity=-1,
            random_state=2026,
            force_col_wise=True,
        )
        model.fit(data[features], data[f"label_{target}"])
        models[target] = model
        print("Historical VAEP fitted", target, len(data), flush=True)
    joblib.dump({"features": features, "models": models}, destination)
    save(
        destination.with_suffix(".json"),
        {
            "training_date": datetime.now(UTC).isoformat(),
            "n_matches": len(matches),
            "n_actions": len(data),
            "cutoff": "2015-08-01",
            "training_match_ids": [m["native_id"] for m in matches],
            "validation": (
                "No standalone VAEP performance claim; complete upstream "
                "stack excluded from result training, calibration, validation"
                " and tournament backtests."
            ),
            "metrics": {},
        },
    )


_BASE = None
_XG = None


def load_worker() -> None:
    global _BASE, _XG
    _BASE = joblib.load(root() / "models/backtest_vaep.joblib")
    for model in _BASE["models"].values():
        model.set_params(n_jobs=1)
    _XG = lgb.Booster(model_file=str(root() / "models/backtest_prematch_xg.txt"))


def feature_match(match: dict) -> list[dict]:
    """Minute boundaries strictly exclude actions at/after that minute."""
    path = output() / f"features/{match['native_id']}.parquet"
    if path.exists():
        return []
    events = json.loads(
        (root() / f"raw/statsbomb/data/events/{match['native_id']}.json").read_text()
    )
    actions = pd.read_parquet(root() / f"processed/spadl/{match['native_id']}.parquet")
    actions = actions[actions.period_id < 3].copy()
    features = pd.read_parquet(
        root() / f"processed/vaep_features/{match['native_id']}.parquet"
    )
    features = features[features.period_id < 3]
    prob = {
        t: m.predict_proba(features[_BASE["features"]])[:, 1]
        for t, m in _BASE["models"].items()
    }
    actions["ps"] = prob["scores"]
    actions["pc"] = prob["concedes"]
    valued = []
    for _, part in actions.groupby("period_id", sort=False):
        part = part.reset_index(drop=True)
        part["vaep"] = value(part, part.ps, part.pc).vaep_value
        valued.append(part)
    actions = pd.concat(valued, ignore_index=True)
    # Shared extracted pre-shot features, predictions regenerated with historical model.
    shots = pd.read_parquet(
        output() / "inplay_shots.parquet",
        filters=[("game_id", "==", match["native_id"])],
    )
    shots["xg"] = _XG.predict(shots[XG_FEATURES], num_threads=1)
    xg = dict(zip(shots.original_event_id, shots.xg, strict=True))
    actions["xg"] = actions.original_event_id.map(xg).fillna(0)
    goals, cards = [], []
    for e in events:
        if e["period"] > 2:
            continue
        side = "home" if e["team"]["id"] == match["home"]["id"] else "away"
        if (
            e["type"]["name"] == "Shot" and e["shot"]["outcome"]["name"] == "Goal"
        ) or e["type"]["name"] == "Own Goal Against":
            if e["type"]["name"] == "Own Goal Against":
                side = "away" if side == "home" else "home"
            goals.append((e["period"], e["minute"] * 60 + e["second"], side))
        card = (
            e.get("foul_committed", {})
            .get("card", e.get("bad_behaviour", {}).get("card", {}))
            .get("name")
        )
        if card in ("Red Card", "Second Yellow"):
            cards.append((e["period"], e["minute"] * 60 + e["second"], side))
    final_h = sum(g[2] == "home" for g in goals)
    final_a = sum(g[2] == "away" for g in goals)
    result = 0 if final_h > final_a else 1 if final_h == final_a else 2
    rows = []
    for period in (1, 2):
        start = 0 if period == 1 else 45
        for minute in range(start, 46 if period == 1 else 91):
            clock = (minute - start) * 60
            past = actions[
                (actions.period_id < period)
                | ((actions.period_id == period) & (actions.time_seconds < clock))
            ]
            recent = past[
                (past.period_id == period) & (past.time_seconds >= clock - 300)
            ]
            row = {
                "match_id": match["match_id"],
                "game_id": match["native_id"],
                "minute": minute,
                "period": period,
                "international": int(match["country"] == "International"),
                "result": result,
                "split": split(match),
            }
            for side in ("home", "away"):
                tid = match[side]["id"]
                row[f"score_{side}"] = sum(
                    g[2] == side
                    and (g[0] < period or (g[0] == period and g[1] < minute * 60))
                    for g in goals
                )
                row[f"red_{side}"] = sum(
                    c[2] == side
                    and (c[0] < period or (c[0] == period and c[1] < minute * 60))
                    for c in cards
                )
                row[f"xg_{side}"] = float(past.loc[past.team_id == tid, "xg"].sum())
                row[f"recent_xg_{side}"] = (
                    float(recent.loc[recent.team_id == tid, "xg"].sum()) / 5
                )
                row[f"recent_vaep_{side}"] = (
                    float(recent.loc[recent.team_id == tid, "vaep"].sum()) / 5
                )
            row["score_diff"] = row["score_home"] - row["score_away"]
            rows.append(row)
    path.parent.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return []


def prepare() -> pd.DataFrame:
    train_base()
    shot_path = output() / "inplay_shots.parquet"
    if not shot_path.exists():
        shots = pd.read_parquet(root() / "processed/xg/shots.parquet")
        shots[shots.period < 3].to_parquet(shot_path, index=False)
    matches = [
        m
        for m in catalogue()
        if m["training"] and split(m) not in ("upstream", "excluded")
    ]
    with ProcessPoolExecutor(
        max_workers=4,
        initializer=load_worker,
        mp_context=multiprocessing.get_context("spawn"),
    ) as pool:
        for i, _ in enumerate(pool.map(feature_match, matches), 1):
            if i % 100 == 0:
                print("In-play feature matches", i, "/", len(matches), flush=True)
    data = pd.concat(
        [
            pd.read_parquet(output() / f"features/{m['native_id']}.parquet")
            for m in matches
        ],
        ignore_index=True,
    )
    data.to_parquet(output() / "inplay_features.parquet", index=False)
    return data


def calibrated(
    model: lgb.LGBMClassifier, x: pd.DataFrame, temperature: float
) -> np.ndarray:
    return softmax(
        np.log(np.clip(model.predict_proba(x), 1e-9, 1)) / temperature, axis=1
    )


def train() -> None:
    data = prepare()
    masks = {
        s: data.split == s for s in ["train", "calibration", "validation", "backtest"]
    }
    report = {
        "training_date": datetime.now(UTC).isoformat(),
        "splits": {
            s: {
                "matches": int(data.loc[k, "game_id"].nunique()),
                "rows": int(k.sum()),
                "match_ids": sorted(data.loc[k, "game_id"].unique().tolist()),
            }
            for s, k in masks.items()
        },
        "metrics": {},
        "features": FEATURES,
        "upstream": (
            "xG and VAEP frozen on 397 pre-August-2015 matches, disjoint "
            "from every result-model split."
        ),
    }
    bundle = {}
    for name, features in [("model", FEATURES), ("baseline", BASELINE)]:
        model = lgb.LGBMClassifier(
            n_estimators=180,
            num_leaves=15,
            learning_rate=0.035,
            min_child_samples=300,
            reg_lambda=10,
            n_jobs=4,
            verbosity=-1,
            random_state=2026,
        )
        model.fit(
            data.loc[masks["train"], features], data.loc[masks["train"], "result"]
        )

        def objective(t: float, model=model, features=features) -> float:
            return scores(
                data.loc[masks["calibration"], "result"].to_numpy(),
                calibrated(model, data.loc[masks["calibration"], features], t),
            )["log_loss"]

        temperature = float(
            minimize_scalar(objective, bounds=(0.5, 3), method="bounded").x
        )
        prob = calibrated(model, data.loc[masks["validation"], features], temperature)
        report["metrics"][name] = {
            **scores(data.loc[masks["validation"], "result"].to_numpy(), prob),
            "temperature": temperature,
        }
        bundle[name] = {
            "model": model,
            "features": features,
            "temperature": temperature,
        }
        print("In-play held-out metrics", name, report["metrics"][name], flush=True)
    destination = root() / "models/backtest_inplay.joblib"
    joblib.dump(bundle, destination)
    save(destination.with_suffix(".json"), report)
    save(output() / "inplay_metrics.json", report)
    test = data.loc[masks["backtest"]].copy()
    p = calibrated(
        bundle["model"]["model"], test[FEATURES], bundle["model"]["temperature"]
    )
    for k, side in enumerate(("home", "draw", "away")):
        test[f"p_{side}"] = p[:, k]
    test.to_parquet(output() / "inplay_predictions.parquet", index=False)
