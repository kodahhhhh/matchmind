"""Frozen, candidate-only pass-completion experiment over raw 360 features."""

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from matchpulse.models.common import catalogue, data_dir, fold_map, timestamp
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import compare, file_hash, freeze_manifest
from matchpulse.models.pass_options import FEATURES, PARAMS, extract_match

CANDIDATE = {
    **PARAMS,
    "n_estimators": 600,
    "num_leaves": 15,
    "min_child_samples": 150,
    "reg_lambda": 10,
    "n_jobs": 8,
}


def run(out: Path) -> dict:
    """Replay the incumbent fit and one fixed candidate on the same five folds."""
    root = data_dir()
    matches = [
        m
        for m in catalogue()
        if (root / f"raw/statsbomb/data/three-sixty/{m['native_id']}.json").exists()
    ]
    inputs = [root / "models/pass_options.json"]
    for m in matches:
        inputs += [
            root / f"raw/statsbomb/data/{kind}/{m['native_id']}.json"
            for kind in ("events", "three-sixty")
        ]
    freeze_manifest(
        out / "split.json",
        {
            "protocol": "fixed recipe, five match folds, raw geometry/360 only",
            "baseline_params": {**PARAMS, "n_jobs": 8},
            "candidate_params": CANDIDATE,
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in inputs},
            "folds": {str(m["native_id"]): fold_map()[m["native_id"]] for m in matches},
        },
    )
    if (out / "pass_options.json").exists():
        raise ValueError("Completed experiment exists")
    path = out / "features.parquet"
    if not path.exists():
        with ProcessPoolExecutor(max_workers=4) as pool:
            data = pd.DataFrame(
                [r for group in pool.map(extract_match, matches) for r in group]
            )
        data.to_parquet(path, index=False)
    data = pd.read_parquet(path)
    freeze_manifest(out / "features.json", {"sha256": file_hash(path)})
    folds = data.game_id.map(fold_map()).to_numpy()
    p, q = np.zeros(len(data)), np.zeros(len(data))
    for f in range(5):
        test = folds == f
        for name, params, pred in [
            ("current", {**PARAMS, "n_jobs": 8}, p),
            ("candidate", CANDIDATE, q),
        ]:
            model = lgb.LGBMClassifier(**params).fit(
                data.loc[~test, FEATURES], data.complete[~test]
            )
            pred[test] = model.predict_proba(data.loc[test, FEATURES])[:, 1]
            model.booster_.save_model(str(out / f"{name}_fold_{f}.txt"))
        print("Pass completion fold", f, flush=True)
    final = lgb.LGBMClassifier(**CANDIDATE).fit(data[FEATURES], data.complete)
    final.booster_.save_model(str(out / "pass_options.txt"))
    report = {
        "training_date": timestamp(),
        "n_matches": int(data.game_id.nunique()),
        "n_passes": len(data),
        "features": FEATURES,
        "params": CANDIDATE,
        "validation": "fixed recipe; incumbent refitted on identical match folds",
        **compare(data.complete.to_numpy(), p, q, data.game_id.to_numpy()),
    }
    report["promotion_recommended"] = all(
        v["ci95"][1] < 0 for v in report["paired_ci"].values()
    )
    data["current"], data["candidate"] = p, q
    data.to_parquet(out / "predictions.parquet", index=False)
    write_report(out / "pass_options.json", report)
    print(
        json.dumps(
            {"metrics": report["metrics"], "paired_ci": report["paired_ci"]}, indent=2
        )
    )
    return report


def main() -> None:
    """Run isolated completion-model comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="passes-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
