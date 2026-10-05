"""Fixed raw-quantile comparison, preserving each outer fold's upstream rebuild.

Primary comparison is p50: it is unchanged by the incumbent band calibration.
Raw p10/p90 are compared separately from archived calibrated production metrics.
"""

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from matchpulse.models.common import data_dir, fold_map, timestamp
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import (
    file_hash,
    freeze_manifest,
    paired_bootstrap,
    quantile_metrics,
)
from matchpulse.models.gamestate_model import (
    FEATURES,
    QUANTILES,
    TARGETS,
    bound_predictions,
)

CANDIDATE = {
    "n_estimators": 360,
    "num_leaves": 7,
    "learning_rate": 0.04,
    "min_child_samples": 300,
    "reg_lambda": 10,
    "n_jobs": 8,
    "verbosity": -1,
    "random_state": 2026,
}
KEYS = ["game_id", "team", "elapsed_end_seconds"]


def run(out: Path) -> dict:
    """Compare a fixed candidate against refitted incumbent raw quantiles."""
    root = data_dir()
    windows_dir = root / "models/candidates/corrected-windows-v1"
    if not (windows_dir / "outputs.json").exists():
        raise ValueError("Build corrected-windows-v1 before game-state evaluation")
    paths = [
        root / "models/gamestate.json",
        windows_dir / "gamestate_windows.parquet",
    ]
    paths += [windows_dir / f"gamestate_windows_fold_{f}.parquet" for f in range(5)]
    card = json.loads(paths[0].read_text())
    original = {**card["params"], "n_jobs": 8}
    freeze_manifest(
        out / "split.json",
        {
            "protocol": "original outer rebuilt windows; fixed raw-quantile recipe",
            "baseline_params": original,
            "candidate_params": CANDIDATE,
            "calibration": "identity factors; incumbent refit on repaired features",
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in paths},
            "fold_map": {str(k): v for k, v in fold_map().items()},
        },
    )
    if (out / "gamestate.json").exists():
        raise ValueError("Completed experiment exists")
    all_rows = pd.read_parquet(paths[1])
    complete = (all_rows.horizon_seconds >= 900) & (all_rows.future_passes > 0)
    rows = all_rows[complete].copy()
    folds = rows.game_id.map(fold_map()).to_numpy()
    predictions = {
        name: {t: np.zeros((len(rows), 3)) for t in TARGETS}
        for name in ("current", "candidate")
    }
    for f in range(5):
        nested = pd.read_parquet(paths[f + 2])[complete]
        if not nested[KEYS].equals(rows[KEYS]):
            raise ValueError("Outer window alignment changed")
        x, test = nested[FEATURES].astype(float), folds == f
        for target in TARGETS:
            y = nested[f"outcome_{target}"].to_numpy()
            rows.loc[test, f"outcome_{target}"] = y[test]
            for name, params in (("current", original), ("candidate", CANDIDATE)):
                for j, quantile in enumerate(QUANTILES):
                    model = lgb.LGBMRegressor(
                        objective="quantile", alpha=quantile, **params
                    )
                    model.fit(x[~test], y[~test])
                    predictions[name][target][test, j] = model.predict(x[test])
                    model.booster_.save_model(
                        str(
                            out / f"{name}_{target}_p{int(100 * quantile)}_fold_{f}.txt"
                        )
                    )
                predictions[name][target][test] = bound_predictions(
                    predictions[name][target][test], target
                )
            print("Game-state completed", f, target, flush=True)
    result = {
        "training_date": timestamp(),
        "features": FEATURES,
        "targets": TARGETS,
        "n_matches": int(rows.game_id.nunique()),
        "n_training_windows": len(rows),
        "params": CANDIDATE,
        "metrics": {},
        "baseline_metrics": {},
        "paired_ci": {},
        "baseline_definition": "incumbent raw quantiles on repaired outer features",
        "historical_invalid_calibrated_metrics": card["metrics"],
        "calibration": {
            "method": "identity, no label fitting",
            "factors": {t: [1.0, 1.0] for t in TARGETS},
        },
        "promotion_recommended": False,
    }
    for target in TARGETS:
        y = rows[f"outcome_{target}"].to_numpy()
        b, c = predictions["current"][target], predictions["candidate"][target]
        result["baseline_metrics"][target], result["metrics"][target] = (
            quantile_metrics(y, b),
            quantile_metrics(y, c),
        )
        result["paired_ci"][target] = {}
        for i, q in enumerate(QUANTILES):
            error_b, error_c = y - b[:, i], y - c[:, i]
            result["paired_ci"][target][f"p{int(100 * q)}"] = paired_bootstrap(
                rows.game_id.to_numpy(),
                np.maximum(q * error_b, (q - 1) * error_b),
                np.maximum(q * error_c, (q - 1) * error_c),
            )
            rows[f"current_{target}_p{int(100 * q)}"] = b[:, i]
            rows[f"candidate_{target}_p{int(100 * q)}"] = c[:, i]
            final = lgb.LGBMRegressor(objective="quantile", alpha=q, **CANDIDATE).fit(
                all_rows.loc[complete, FEATURES].astype(float),
                all_rows.loc[complete, f"outcome_{target}"],
            )
            final.booster_.save_model(
                str(out / f"gamestate_{target}_p{int(100 * q)}.txt")
            )
    rows.to_parquet(out / "predictions.parquet", index=False)
    write_report(out / "gamestate.json", result)
    print(
        json.dumps(
            {"metrics": result["metrics"], "paired_ci": result["paired_ci"]}, indent=2
        )
    )
    return result


def main() -> None:
    """Run candidate-local quantile experiment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="gamestate-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
