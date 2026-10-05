"""Candidate-only nested match-fold xG search, with incumbent artifact replay."""

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from matchpulse.models.common import data_dir, fold_map, timestamp
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import compare, file_hash, freeze_manifest, losses
from matchpulse.models.xg import CATEGORIES, FEATURES

RECIPES = [
    {
        "name": name,
        "n_estimators": trees,
        "num_leaves": leaves,
        "min_child_samples": child,
        "reg_lambda": penalty,
    }
    for name, trees, leaves, child, penalty in [
        ("incumbent", 350, 15, 150, 5),
        ("small", 350, 7, 150, 10),
        ("small_long", 700, 7, 200, 10),
        ("smooth", 500, 15, 300, 20),
        ("wide", 350, 31, 200, 20),
        ("short", 180, 15, 150, 10),
    ]
]


def masks(
    folds: np.ndarray, eligible: np.ndarray, outer: int
) -> tuple[np.ndarray, ...]:
    """Inner training/selection exclude every row of the outer test matches."""
    inner = (outer + 1) % 5
    return (
        (folds != outer) & (folds != inner) & eligible,
        (folds == inner) & eligible,
        folds == outer,
    )


def fit(recipe: dict, x: pd.DataFrame, y: pd.Series) -> lgb.LGBMClassifier:
    """Fit one bounded, deterministic recipe with the incumbent feature schema."""
    params = {k: v for k, v in recipe.items() if k != "name"}
    return lgb.LGBMClassifier(
        **params, learning_rate=0.035, n_jobs=8, verbosity=-1, random_state=2026
    ).fit(x, y)


def run(out: Path) -> dict:
    """Execute a fixed nested selection procedure and save compatible boosters."""
    root = data_dir()
    source = root / "processed/xg/shots.parquet"
    rows = pd.read_parquet(source)
    folds = rows.game_id.map(fold_map()).to_numpy()
    if not np.array_equal(rows.fold, folds):
        raise ValueError("xG fold assignments changed")
    eligible = (rows.period < 5).to_numpy()
    paths = [
        source,
        root / "models/xg.json",
        *[root / f"models/xg_fold_{f}.txt" for f in range(5)],
    ]
    freeze_manifest(
        out / "split.json",
        {
            "protocol": (
                "five outer match folds; next fold inner selection; remaining three fit"
            ),
            "recipes": RECIPES,
            "features": FEATURES,
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in paths},
            "folds": {
                str(f): sorted(rows.loc[folds == f, "game_id"].unique().tolist())
                for f in range(5)
            },
            "selection": (
                "minimum inner log loss; production recipe from outer-0 inner selection"
            ),
        },
    )
    if (out / "xg.json").exists():
        raise ValueError("Completed experiment exists; do not retune its test folds")
    x, y = rows[FEATURES], rows.goal
    current, candidate = np.zeros(len(rows)), np.zeros(len(rows))
    selection, selected_recipes = [], []
    for outer in range(5):
        train, tune, test = masks(folds, eligible, outer)
        scores = []
        for recipe in RECIPES:
            model = fit(recipe, x[train], y[train])
            p = model.predict_proba(x[tune])[:, 1]
            score = float(losses(y[tune].to_numpy(), p)["log_loss"].mean())
            scores.append(score)
            print("inner", outer, recipe["name"], score, flush=True)
        best = int(np.argmin(scores))
        selected_recipes.append(RECIPES[best])
        selection.append(
            {
                "outer": outer,
                "inner": (outer + 1) % 5,
                "scores": dict(zip([r["name"] for r in RECIPES], scores, strict=True)),
                "selected": RECIPES[best],
            }
        )
        # No outer score is inspected until all folds' choices have been locked.
        freeze_manifest(out / f"selection_{outer}.json", selection[-1])
        model = fit(RECIPES[best], x[~test & eligible], y[~test & eligible])
        candidate[test] = model.predict_proba(x[test])[:, 1]
        model.booster_.save_model(str(out / f"xg_fold_{outer}.txt"))
        baseline = lgb.Booster(model_file=str(root / f"models/xg_fold_{outer}.txt"))
        current[test] = baseline.predict(x[test], num_threads=8)
    # The production recipe is fixed by the first inner selection, not outer results.
    final = fit(selected_recipes[0], x[eligible], y[eligible])
    final.booster_.save_model(str(out / "xg.txt"))
    rows["baseline_xg"], rows["xg"] = current, candidate
    rows.to_parquet(out / "shots.parquet", index=False)
    result = {
        "training_date": timestamp(),
        "n_matches": int(rows.game_id.nunique()),
        "n_shots": int(eligible.sum()),
        "features": FEATURES,
        "categories": CATEGORIES,
        "params": selected_recipes[0],
        "selections": selection,
        "validation": "nested match-fold recipe selection; shootouts excluded",
        **compare(
            y[eligible].to_numpy(),
            current[eligible],
            candidate[eligible],
            rows.loc[eligible, "game_id"].to_numpy(),
        ),
        "promotion_recommended": False,
    }
    # Segment reporting is diagnostic only, never used to select or refit.
    result["segments"] = {}
    for name, mask in {
        "with_freeze_frame": rows.freeze_frame_present == 1,
        "without_freeze_frame": rows.freeze_frame_present == 0,
        "penalties": rows.shot_type == CATEGORIES["shot_type"].index("Penalty"),
    }.items():
        ev = mask.to_numpy() & eligible
        if ev.any():
            result["segments"][name] = compare(
                y[ev].to_numpy(),
                current[ev],
                candidate[ev],
                rows.loc[ev, "game_id"].to_numpy(),
            )
    write_report(out / "xg.json", result)
    print(
        json.dumps(
            {"metrics": result["metrics"], "paired_ci": result["paired_ci"]}, indent=2
        )
    )
    return result


def main() -> None:
    """Run one saved candidate experiment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="xg-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
