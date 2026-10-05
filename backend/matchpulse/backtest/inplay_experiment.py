"""W14 candidate-only in-play training with chronological selection/calibration."""

import argparse
import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import softmax

from matchpulse.backtest.inplay import BASELINE, FEATURES
from matchpulse.models.common import data_dir, timestamp
from matchpulse.models.evaluate import (
    bundle_predict,
    destination,
    inplay,
    inplay_data,
    write_report,
)
from matchpulse.models.evaluation import freeze_manifest, losses, probability_metrics

# Fixed before viewing validation. No test-set search loop.
RECIPES = [
    {"name": name, "features": features, "leaves": leaves, "trees": trees}
    for name, features, leaves, trees in [
        ("score7", BASELINE, 7, 180),
        ("score15", BASELINE, 15, 350),
        ("state7", BASELINE + ["red_home", "red_away", "international"], 7, 180),
        ("state15", BASELINE + ["red_home", "red_away", "international"], 15, 350),
        ("full7", FEATURES, 7, 180),
        ("full15", FEATURES, 15, 350),
    ]
]


def run(out: Path) -> dict:
    """Select on 2018, calibrate on 2019, then evaluate once."""
    data = inplay_data(out)
    catalogue = json.loads((data_dir() / "catalogue/matches.json").read_text())
    dates = data.game_id.map({m["native_id"]: m["match_date"] for m in catalogue})
    train = data.split == "train"
    tune = (data.split == "calibration") & (dates < "2019-01-01")
    calibrate = (data.split == "calibration") & (dates >= "2019-01-01")
    if not train.any() or not tune.any() or not calibrate.any():
        raise ValueError("Empty chronological development partition")
    freeze_manifest(
        out / "experiment.json",
        {
            "recipes": RECIPES,
            "selection": "2018 raw log loss, no test access",
            "calibration": "temperature on 2019 only; classifier remains pre-2018",
            "tuning_match_ids": sorted(data.loc[tune, "game_id"].unique().tolist()),
            "calibration_match_ids": sorted(
                data.loc[calibrate, "game_id"].unique().tolist()
            ),
        },
    )
    if (out / "backtest_inplay.joblib").exists():
        raise ValueError("Candidate already fitted; rerun evaluation, not selection")
    models, results = [], []
    for recipe in RECIPES:
        model = lgb.LGBMClassifier(
            n_estimators=recipe["trees"],
            num_leaves=recipe["leaves"],
            learning_rate=0.035,
            min_child_samples=500,
            reg_lambda=20,
            n_jobs=8,
            verbosity=-1,
            random_state=2026,
        )
        model.fit(data.loc[train, recipe["features"]], data.loc[train, "result"])
        p = model.predict_proba(data.loc[tune, recipe["features"]])
        metrics = probability_metrics(data.loc[tune, "result"].to_numpy(), p)
        results.append({**recipe, "metrics": metrics})
        models.append(model)
        print(
            recipe["name"], {k: metrics[k] for k in ("brier", "log_loss")}, flush=True
        )
        write_report(out / "development.json", {"results": results})
    selected = min(range(len(results)), key=lambda i: results[i]["metrics"]["log_loss"])
    recipe, model = RECIPES[selected], models[selected]
    raw = model.predict_proba(data.loc[calibrate, recipe["features"]])
    logits = np.log(np.clip(raw, 1e-9, 1))
    y = data.loc[calibrate, "result"].to_numpy()
    fitted = minimize_scalar(
        lambda t: losses(y, softmax(logits / t, axis=1))["log_loss"].mean(),
        bounds=(0.5, 3),
        method="bounded",
    )
    if not fitted.success:
        raise ValueError("Temperature fit failed")
    incumbent = joblib.load(data_dir() / "models/backtest_inplay.joblib")
    bundle = {
        "model": {
            "model": model,
            "features": recipe["features"],
            "temperature": float(fitted.x),
        },
        "baseline": incumbent["baseline"],
    }
    artifact = out / "backtest_inplay.joblib"
    joblib.dump(bundle, artifact)
    freeze_manifest(
        out / "selection.json", {"selected": recipe, "temperature": float(fitted.x)}
    )
    evaluation = inplay(out, artifact)
    report = {
        "training_date": timestamp(),
        "n_matches": int(data.loc[train, "game_id"].nunique()),
        "n_rows": int(train.sum()),
        "features": recipe["features"],
        "selected": recipe,
        "temperature": float(fitted.x),
        **evaluation["splits"]["validation"]["comparison"],
        "vs_naive": evaluation["splits"]["validation"]["vs_naive"],
        "tournaments": evaluation["splits"]["backtest"],
        "validation": (
            "pre-2018 fit; 2018 selection; 2019 calibration; 2020-2022 evaluation"
        ),
        "promotion_recommended": False,
    }
    write_report(artifact.with_suffix(".json"), report)
    test = data[data.split == "backtest"].copy()
    p = bundle_predict(bundle, test)
    for k, side in enumerate(("home", "draw", "away")):
        test[f"p_{side}"] = p[:, k]
    test.to_parquet(out / "inplay_predictions.parquet", index=False)
    print(
        json.dumps(
            {
                "selected": recipe["name"],
                "metrics": report["metrics"],
                "paired_ci": report["paired_ci"],
            },
            indent=2,
        ),
        flush=True,
    )
    return report


def main() -> None:
    """Start one frozen experiment in an isolated candidate directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="inplay-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
