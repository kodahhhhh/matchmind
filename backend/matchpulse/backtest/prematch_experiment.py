"""Frozen pre-match correction search, selected only on walk-forward weeks 6–17."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from matchpulse.backtest.squad_train import offset_predict
from matchpulse.models.common import data_dir, timestamp
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import (
    compare,
    file_hash,
    freeze_manifest,
    probability_metrics,
)
from matchpulse.models.squad import SQUAD_FEATURES

VALUE = [
    "xi_log_total_diff",
    "xi_mean_log_diff",
    "bench_log_total_diff",
    "xi_log_total_level",
]
RECIPES = [
    {"name": name, "features": features, "penalty": penalty}
    for name, features, penalty in [
        ("incumbent", VALUE, 100.0),
        ("value300", VALUE, 300.0),
        ("value1000", VALUE, 1000.0),
        ("value30", VALUE, 30.0),
        ("age300", [*VALUE, "mean_age_diff", "mean_age_level"], 300.0),
        ("all300", SQUAD_FEATURES, 300.0),
    ]
]


def run(out: Path) -> dict:
    """Select one correction before scoring the complete evaluation rounds."""
    root = data_dir()
    base_path = root / "processed/backtest/w12_before/prematch_predictions.json"
    current_path = root / "processed/backtest/prematch_predictions.json"
    squad_path = root / "processed/backtest/squad_prematch.parquet"
    original = pd.DataFrame(json.loads(base_path.read_text()))
    current = (
        pd.DataFrame(json.loads(current_path.read_text()))
        .set_index("match_id")
        .loc[original.match_id]
    )
    data = original.merge(
        pd.read_parquet(squad_path), on="match_id", validate="one_to_one", sort=False
    )
    if not np.array_equal(data.result, current.result):
        raise ValueError("Current pre-match labels differ")
    freeze_manifest(
        out / "split.json",
        {
            "protocol": (
                "earlier-round fits; tune weeks 6-17; freeze correction after week 17"
            ),
            "recipes": RECIPES,
            "selection": "minimum tuning log loss",
            "inputs": {
                str(p.relative_to(root)): file_hash(p)
                for p in [base_path, current_path, squad_path]
            },
            "tune_match_ids": sorted(
                data.loc[data["round"].between(6, 17), "match_id"]
            ),
            "test_match_ids": sorted(data.loc[data["round"] >= 18, "match_id"]),
        },
    )
    if (out / "backtest_squad_prematch.json").exists():
        raise ValueError("Completed experiment exists")
    y, base = data.result.to_numpy(), np.array(data.model.tolist())
    tune = data["round"].between(6, 17).to_numpy()
    test = (data["round"] >= 18).to_numpy()
    forecasts, scores = [], []
    for recipe in RECIPES:
        p, x = base.copy(), data[recipe["features"]].to_numpy(float)
        for week in range(6, 35):
            train = (data["round"] < min(week, 18)).to_numpy()
            target = (data["round"] == week).to_numpy()
            p[target] = offset_predict(
                x[train],
                y[train],
                base[train],
                x[target],
                base[target],
                recipe["penalty"],
            )
        forecasts.append(p)
        score = probability_metrics(y[tune], p[tune])
        scores.append(score)
        print(recipe["name"], score["log_loss"], flush=True)
    best = min(range(len(scores)), key=lambda i: scores[i]["log_loss"])
    freeze_manifest(
        out / "selection.json", {"selected": RECIPES[best], "tuning": scores}
    )
    groups = data.loc[test, "match_id"].to_numpy()
    p, q = np.array(current.model.tolist())[test], forecasts[best][test]
    market = 1 / np.array(data.loc[test, "closing"].tolist())
    market /= market.sum(axis=1, keepdims=True)
    result = {
        "training_date": timestamp(),
        "n_matches": len(data),
        "n_evaluation_matches": int(test.sum()),
        "selected": RECIPES[best],
        "validation": "walk-forward tuning; untouched weeks 18-34",
        **compare(y[test], p, q, groups),
        "vs_market": compare(y[test], market, q, groups),
        "incumbent_recipe_max_abs_reproduction_error": float(
            np.max(np.abs(forecasts[0][test] - p))
        ),
    }
    result["promotion_recommended"] = all(
        v["ci95"][1] < 0 for v in result["paired_ci"].values()
    )
    original["model"] = list(forecasts[best])
    write_report(out / "backtest_squad_prematch.json", result)
    (out / "prematch_predictions.json").write_text(
        original.to_json(orient="records", indent=2)
    )
    print(
        json.dumps(
            {"selected": RECIPES[best]["name"], "paired_ci": result["paired_ci"]},
            indent=2,
        )
    )
    return result


def main() -> None:
    """Run candidate-only pre-match comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="prematch-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
