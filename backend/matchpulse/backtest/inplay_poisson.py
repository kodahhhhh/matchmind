"""Fixed distributional in-play candidate with a fresh chronological holdout.

The original validation cohort is now diagnostic only. No recipe search occurs.
Upstream models remain the original pre-August-2015 fits. Local input reads only.
"""

import argparse
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow as pa
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from scipy.stats import skellam

from matchpulse.backtest.inplay import FEATURES, feature_frame, load_worker, split
from matchpulse.models.common import catalogue, data_dir, timestamp
from matchpulse.models.evaluate import (
    bundle_predict,
    destination,
    inplay_data,
    inplay_markets,
    write_report,
)
from matchpulse.models.evaluation import compare, file_hash, freeze_manifest, losses

PARAMS = {
    "objective": "poisson",
    "n_estimators": 400,
    "num_leaves": 15,
    "learning_rate": 0.035,
    "min_child_samples": 500,
    "reg_lambda": 20,
    "n_jobs": 8,
    "verbosity": -1,
    "random_state": 2026,
}


def exposure(rows: pd.DataFrame) -> np.ndarray:
    """Fixed 90-minute scale including three expected remaining added minutes."""
    return (np.maximum(90 - rows.minute.to_numpy(), 0) + 3) / 90


def perspective(rows: pd.DataFrame, side: str) -> pd.DataFrame:
    """Symmetric pre-minute context, with explicit home advantage."""
    other = "away" if side == "home" else "home"
    out = rows[["minute", "period", "international"]].copy()
    out["is_home"] = int(side == "home")
    for feature in ("score", "red", "xg", "recent_xg", "recent_vaep"):
        out[f"{feature}_for"] = rows[f"{feature}_{side}"]
        out[f"{feature}_against"] = rows[f"{feature}_{other}"]
    out["score_diff"] = out.score_for - out.score_against
    return out


class PoissonResult:
    """Compatible classifier interface backed by symmetric actual-goal rates."""

    def __init__(self, regressor: lgb.LGBMRegressor) -> None:
        self.regressor = regressor

    def set_params(self, *, n_jobs: int) -> "PoissonResult":
        self.regressor.set_params(n_jobs=n_jobs)
        return self

    def predict_proba(self, rows: pd.DataFrame) -> np.ndarray:
        rates = [
            np.maximum(self.regressor.predict(perspective(rows, side)), 1e-10)
            * exposure(rows)
            for side in ("home", "away")
        ]
        return result_probabilities(rows.score_diff.to_numpy(), *rates)


def result_probabilities(
    score_diff: np.ndarray, home_rate: np.ndarray, away_rate: np.ndarray
) -> np.ndarray:
    """Independent Poisson remaining goals, including the entire count tail."""
    h, a = np.maximum(home_rate, 1e-10), np.maximum(away_rate, 1e-10)
    away = skellam.cdf(-score_diff - 1, h, a)
    draw = skellam.pmf(-score_diff, h, a)
    home = skellam.sf(-score_diff, h, a)
    p = np.maximum(np.column_stack([home, draw, away]), 0)
    return p / p.sum(axis=1, keepdims=True)


def regulation_goals(match: dict, events: list[dict]) -> tuple[int, int]:
    """Count actual regulation goals, reversing own goals and excluding extra time."""
    total = {"home": 0, "away": 0}
    for event in events:
        if event["period"] > 2:
            continue
        side = "home" if event["team"]["id"] == match["home"]["id"] else "away"
        if event["type"]["name"] == "Own Goal Against":
            total["away" if side == "home" else "home"] += 1
        elif (
            event["type"]["name"] == "Shot"
            and event["shot"]["outcome"]["name"] == "Goal"
        ):
            total[side] += 1
    return total["home"], total["away"]


def _initialize() -> None:
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    load_worker()


def fresh_matches() -> list[dict]:
    """Identity/date-only fresh cohort; selected before outcome extraction."""
    return [
        m
        for m in catalogue()
        if split(m) == "excluded"
        and m["match_date"]
        and m["match_date"] >= "2022-11-01"
    ]


def run(out: Path) -> dict:
    """Fit once on pre-2018 data, calibrate pre-2020, evaluate new later matches."""
    root = data_dir()
    old = inplay_data(out)
    future = fresh_matches()
    known = {m["native_id"]: m for m in catalogue()}
    paths = [root / "processed/backtest/inplay_shots.parquet"]
    # Pin every training-label file, plus the new cohort's feature inputs.
    paths += [
        root / f"raw/statsbomb/data/events/{game}.json"
        for game in sorted(set(old.game_id) | {m["native_id"] for m in future})
    ]
    paths += [
        root / f"processed/{kind}/{m['native_id']}.parquet"
        for m in future
        for kind in ("spadl", "vaep_features")
    ]
    future_ids = {m["native_id"] for m in future}
    if future_ids & set(old.game_id):
        raise ValueError("Fresh cohort overlaps earlier evaluation")
    for name in ("backtest_vaep", "backtest_prematch_xg"):
        upstream = json.loads((root / f"models/{name}.json").read_text())
        if future_ids & set(upstream["training_match_ids"]):
            raise ValueError("Fresh matches entered upstream training")
    freeze_manifest(
        out / "distributional_protocol.json",
        {
            "params": PARAMS,
            "exposure": "(max(90-minute, 0)+3)/90; fixed before fitting",
            "selection": "one recipe, no search; pooled home/away perspective",
            "fit": "original pre-2018 partition",
            "calibration": "temperature on original 2018-2019 partition only",
            "primary": "previously excluded dated matches from 2022-11-01 onward",
            "future_matches": [m["match_id"] for m in future],
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in paths},
            "limits": "Selected teams/competitions; not representative of all fixtures",
        },
    )
    if (out / "backtest_inplay.json").exists():
        raise ValueError("Completed candidate exists")
    fresh_path = out / "fresh_features.parquet"
    if fresh_path.exists():
        fresh = pd.read_parquet(fresh_path)
    else:
        with ProcessPoolExecutor(
            max_workers=4,
            initializer=_initialize,
            mp_context=multiprocessing.get_context("spawn"),
        ) as pool:
            frames = list(pool.map(feature_frame, future))
        fresh = pd.concat(frames, ignore_index=True)
        fresh.to_parquet(fresh_path, index=False)
    # Assert extractor refactoring exactly reproduces an existing cached match.
    _initialize()
    example = old.game_id.iloc[0]
    replay = feature_frame(known[example])
    columns = list(old.columns)
    pd.testing.assert_frame_equal(
        replay[columns].reset_index(drop=True),
        old.loc[old.game_id == example, columns].reset_index(drop=True),
        check_dtype=False,
    )
    data = pd.concat([old, fresh], ignore_index=True)
    goals = {}
    for game in data.game_id.unique():
        events = json.loads(
            (root / f"raw/statsbomb/data/events/{game}.json").read_text()
        )
        goals[game] = regulation_goals(known[game], events)
    for i, side in enumerate(("home", "away")):
        data[f"remaining_{side}"] = (
            data.game_id.map({game: g[i] for game, g in goals.items()})
            - data[f"score_{side}"]
        )
        if (data[f"remaining_{side}"] < 0).any():
            raise ValueError("Negative remaining-goal target")
    actual = np.array([0 if h > a else 1 if h == a else 2 for h, a in goals.values()])
    if (
        not data.game_id.map(dict(zip(goals, actual, strict=True)))
        .eq(data.result)
        .all()
    ):
        raise ValueError("Regulation-goal labels disagree with current result labels")
    train = data[data.split == "train"]
    e = exposure(train)
    x = pd.concat([perspective(train, s) for s in ("home", "away")], ignore_index=True)
    y = np.concatenate(
        [train[f"remaining_{s}"].to_numpy() / e for s in ("home", "away")]
    )
    regressor = lgb.LGBMRegressor(**PARAMS).fit(x, y, sample_weight=np.tile(e, 2))
    # Import by canonical module name so joblib never records a __main__ class.
    from matchpulse.backtest.inplay_poisson import PoissonResult as SavedPoissonResult

    model = SavedPoissonResult(regressor)
    calibration = data[data.split == "calibration"]
    raw = model.predict_proba(calibration)
    logits = np.log(np.clip(raw, 1e-9, 1))
    fitted = minimize_scalar(
        lambda t: losses(calibration.result.to_numpy(), softmax(logits / t, axis=1))[
            "log_loss"
        ].mean(),
        bounds=(0.5, 3),
        method="bounded",
    )
    if not fitted.success:
        raise ValueError("Temperature fit failed")
    current = joblib.load(root / "models/backtest_inplay.joblib")
    candidate = {
        "model": {"model": model, "features": FEATURES, "temperature": float(fitted.x)},
        "baseline": current["baseline"],
    }
    artifact = out / "backtest_inplay.joblib"
    joblib.dump(candidate, artifact)
    candidate = joblib.load(artifact)
    results = {}
    for name, selected in [
        ("fresh", data.game_id.isin(future_ids)),
        ("old_validation_diagnostic", data.split == "validation"),
        ("tournaments_diagnostic", data.split == "backtest"),
    ]:
        rows = data[selected].copy()
        p, q = bundle_predict(current, rows), bundle_predict(candidate, rows)
        naive = bundle_predict(current, rows, "baseline")
        y, ids = rows.result.to_numpy(), rows.game_id.to_numpy()
        results[name] = {
            "n_matches": int(rows.game_id.nunique()),
            **compare(y, p, q, ids),
            "vs_naive": compare(y, naive, q, ids),
        }
        for k, side in enumerate(("home", "draw", "away")):
            rows[f"candidate_{side}"] = q[:, k]
            rows[f"current_{side}"] = p[:, k]
            rows[f"naive_{side}"] = naive[:, k]
        rows.to_parquet(out / f"{name}_predictions.parquet", index=False)
    report = {
        "training_date": timestamp(),
        "n_matches": int(train.game_id.nunique()),
        "n_rows": len(train),
        "features": FEATURES,
        "params": PARAMS,
        "temperature": float(fitted.x),
        "baseline_metrics": results["fresh"]["baseline_metrics"],
        "metrics": results["fresh"]["metrics"],
        "paired_ci": results["fresh"]["paired_ci"],
        "cohorts": results,
        "market_checkpoints": inplay_markets(old, current, candidate, out),
        "promotion_recommended": False,
        "validation": (
            "fresh chronological cohort; old tests diagnostic, never recipe tuning"
        ),
        "modelled": True,
    }
    write_report(out / "backtest_inplay.json", report)
    print(json.dumps({"fresh": results["fresh"]["paired_ci"]}, indent=2), flush=True)
    return report


def main() -> None:
    """Run the predeclared candidate with bounded resources."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="inplay-poisson-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
