"""One frozen goals recipe against a faithful fold-rebuilt incumbent refit."""

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.special import gammaln, xlogy

from matchpulse.models.common import data_dir, fold_map, timestamp
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import (
    compare,
    file_hash,
    freeze_manifest,
    paired_bootstrap,
)
from matchpulse.models.goals import (
    FEATURES,
    PARAMS,
    TARGETS,
    add_targets,
    outcome_probs,
)

CANDIDATE = {
    **PARAMS,
    "n_estimators": 500,
    "num_leaves": 7,
    "min_child_samples": 500,
    "reg_lambda": 20,
    "n_jobs": 8,
}
KEYS = ["game_id", "team", "elapsed_end_seconds"]


def poisson_losses(y: np.ndarray, mu: np.ndarray) -> dict[str, np.ndarray]:
    """Actual-count proper scores, including zero-goal observations."""
    if not np.isfinite(mu).all() or (mu <= 0).any():
        raise ValueError("Poisson rates must be finite and positive")
    return {
        "poisson_deviance": 2 * (xlogy(y, y / mu) - y + mu),
        "poisson_log_loss": mu - xlogy(y, mu) + gammaln(y + 1),
    }


def run(out: Path) -> dict:
    """Refit both recipes on each original outer-fold feature rebuild."""
    root = data_dir()
    paths = [
        root / "processed/gamestate_windows.parquet",
        root / "models/goals.json",
        root / "catalogue/matches.json",
    ]
    for f in range(5):
        paths += [
            root / f"processed/gamestate_windows_fold_{f}.parquet",
            root / f"processed/gamestate_windows_fold_{f}.provenance.json",
        ]
    freeze_manifest(
        out / "split.json",
        {
            "protocol": (
                "fixed recipe; same five folds and incumbent fold-rebuilt upstream"
            ),
            "baseline_params": {**PARAMS, "n_jobs": 8},
            "candidate_params": CANDIDATE,
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in paths},
            "fold_map": {str(k): v for k, v in fold_map().items()},
        },
    )
    if (out / "goals.json").exists():
        raise ValueError("Completed experiment exists")
    target_path = out / "targets.parquet"
    if not target_path.exists():
        add_targets(pd.read_parquet(paths[0])).to_parquet(target_path, index=False)
    production = pd.read_parquet(target_path)
    freeze_manifest(out / "targets.json", {"sha256": file_hash(target_path)})
    folds = production.game_id.map(fold_map()).to_numpy()
    base = {t: np.zeros(len(production)) for t in TARGETS}
    candidate = {t: np.zeros(len(production)) for t in TARGETS}
    ok = {
        t: (
            (production.horizon_seconds >= 900).to_numpy()
            if t == "goals_next15"
            else np.ones(len(production), bool)
        )
        for t in TARGETS
    }
    for f in range(5):
        nested = pd.read_parquet(root / f"processed/gamestate_windows_fold_{f}.parquet")
        if not nested[KEYS].equals(production[KEYS]):
            raise ValueError("Outer fold window alignment changed")
        for col in ("block_minutes_left", "is_extra_time"):
            nested[col] = production[col].to_numpy()
        test = folds == f
        x = nested[FEATURES].astype(float)
        for t in TARGETS:
            y = production[t].to_numpy()
            for name, params, predictions in [
                ("current", {**PARAMS, "n_jobs": 8}, base),
                ("candidate", CANDIDATE, candidate),
            ]:
                artifact = out / f"{name}_{t}_fold_{f}.txt"
                if artifact.exists():
                    booster = lgb.Booster(model_file=str(artifact))
                else:
                    model = lgb.LGBMRegressor(**params).fit(
                        x[~test & ok[t]], y[~test & ok[t]]
                    )
                    booster = model.booster_
                    booster.save_model(str(artifact))
                predictions[t][test] = booster.predict(x[test], num_threads=8)
            print("completed fold", f, t, flush=True)
    report = {
        "training_date": timestamp(),
        "n_matches": int(production.game_id.nunique()),
        "n_windows": len(production),
        "features": FEATURES,
        "params": CANDIDATE,
        "baseline_metrics": {},
        "metrics": {},
        "paired_ci": {},
        "validation": "fixed recipe on five original fold-rebuilt match folds",
        "promotion_recommended": False,
    }
    for t in TARGETS:
        y = production.loc[ok[t], t].to_numpy()
        groups = production.loc[ok[t], "game_id"].to_numpy()
        b, c = base[t][ok[t]], candidate[t][ok[t]]
        bl, cl = poisson_losses(y, b), poisson_losses(y, c)
        report["baseline_metrics"][t] = {k: float(v.mean()) for k, v in bl.items()}
        report["metrics"][t] = {k: float(v.mean()) for k, v in cl.items()}
        report["paired_ci"][t] = {k: paired_bootstrap(groups, bl[k], cl[k]) for k in bl}
        report["metrics"][t]["scoring_probability"] = compare(
            (y > 0).astype(int), -np.expm1(-b), -np.expm1(-c), groups
        )
        final = lgb.LGBMRegressor(**CANDIDATE).fit(
            production.loc[ok[t], FEATURES], production.loc[ok[t], t]
        )
        final.booster_.save_model(str(out / f"goals_{t}.txt"))
        production[f"baseline_{t}"], production[f"candidate_{t}"] = (
            base[t],
            candidate[t],
        )
    home = production[production.team == "home"].set_index(
        ["game_id", "elapsed_end_seconds"]
    )
    away = (
        production[production.team == "away"]
        .set_index(home.index.names)
        .reindex(home.index)
    )
    diff = home.score_diff.to_numpy()
    final_diff = diff + home.goals_rest.to_numpy() - home.goals_rest_against.to_numpy()
    y = np.where(final_diff > 0, 0, np.where(final_diff == 0, 1, 2))
    p = {
        name: outcome_probs(
            home[f"{name}_goals_rest"].to_numpy(),
            away[f"{name}_goals_rest"].to_numpy(),
            diff,
        )
        for name in ("baseline", "candidate")
    }
    report["block_result_truncation"] = {
        name: {
            "maximum_missing_mass": float(np.max(1 - prob.sum(axis=1))),
            "mean_missing_mass": float(np.mean(1 - prob.sum(axis=1))),
        }
        for name, prob in p.items()
    }
    # The existing API truncates each Poisson at 12. Report that limitation,
    # then normalize both sides identically for proper probability scoring.
    p = {name: prob / prob.sum(axis=1, keepdims=True) for name, prob in p.items()}
    report["block_result"] = compare(
        y,
        p["baseline"],
        p["candidate"],
        home.index.get_level_values("game_id").to_numpy(),
    )
    report["promotion_recommended"] = all(
        report["paired_ci"][target]["poisson_deviance"]["ci95"][1] < 0
        for target in TARGETS
    ) and all(
        result["ci95"][1] < 0 for result in report["block_result"]["paired_ci"].values()
    )
    production.to_parquet(out / "predictions.parquet", index=False)
    write_report(out / "goals.json", report)
    print(
        json.dumps(
            {"metrics": report["metrics"], "paired_ci": report["paired_ci"]}, indent=2
        )
    )
    return report


def main() -> None:
    """Run a candidate without rebuilding or writing any production cache."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="goals-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
