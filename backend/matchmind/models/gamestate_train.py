"""Train quantile forecasts with an outer match holdout for the entire stack.

For each outer fold, windows for BOTH train and test matches are rebuilt using
xG/VAEP models fitted only on the outer training matches. This avoids indirect
held-out outcome leakage through upstream predictions. Final production models
use the all-match out-of-fold artifact. No calibration uses test outcomes.
"""

import json

import lightgbm as lgb
import numpy as np
from sklearn.metrics import mean_pinball_loss

from matchmind.models.common import data_dir, fold_map, save_json, timestamp
from matchmind.models.gamestate_model import (
    BASE_FEATURES,
    FEATURES,
    QUANTILES,
    TARGETS,
    bound_predictions,
    calibrate,
    featurize,
)
from matchmind.models.windows import load_or_build

FACTORS = np.round(np.arange(0.3, 2.01, 0.02), 2)


def fit_factors(y: np.ndarray, p: np.ndarray, target: str) -> list[float]:
    """Scale p10/p90 distance from p50 to minimise each quantile's pinball loss."""
    best = []
    for j, (i, alpha) in enumerate(((0, 0.1), (2, 0.9))):
        losses = []
        for f in FACTORS:
            factors = [f, 1.0] if j == 0 else [1.0, f]
            q = calibrate(p, target, factors)[:, i]
            losses.append(mean_pinball_loss(y, q, alpha=alpha))
        best.append(float(FACTORS[int(np.argmin(losses))]))
    return best


def evaluate(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "pinball": {
            f"p{int(q * 100)}": float(mean_pinball_loss(y, p[:, i], alpha=q))
            for i, q in enumerate(QUANTILES)
        },
        "coverage_p10_p90": float(((y >= p[:, 0]) & (y <= p[:, 2])).mean()),
        "mean_width": float((p[:, 2] - p[:, 0]).mean()),
        "n": len(y),
        "zero_outcomes": float((y == 0).mean()),
    }


def main() -> None:
    all_windows = load_or_build()
    # Entire 15-minute horizon must be observed; no late-game zero padding.
    complete = (all_windows.horizon_seconds >= 900) & (all_windows.future_passes > 0)
    windows = all_windows[complete].copy()
    folds = windows.game_id.map(fold_map()).to_numpy()
    predictions = {target: np.zeros((len(windows), 3)) for target in TARGETS}
    base_predictions = {target: np.zeros((len(windows), 3)) for target in TARGETS}
    constant = {target: np.zeros((len(windows), 3)) for target in TARGETS}
    outcomes = {target: np.zeros(len(windows)) for target in TARGETS}
    score_shift = np.zeros(len(windows))
    params = dict(
        n_estimators=180,
        num_leaves=15,
        learning_rate=0.04,
        min_child_samples=200,
        reg_lambda=5,
        n_jobs=16,
        verbosity=-1,
        random_state=2026,
    )
    fold_metrics = []
    for fold in range(5):
        nested = load_or_build(fold)
        nested = nested[complete].copy()
        assert nested[["game_id", "team", "elapsed_end_seconds"]].equals(
            windows[["game_id", "team", "elapsed_end_seconds"]]
        )
        x = featurize(nested)
        test = folds == fold
        for target in TARGETS:
            y = nested[f"outcome_{target}"].to_numpy()
            outcomes[target][test] = y[test]
            for j, quantile in enumerate(QUANTILES):
                model = lgb.LGBMRegressor(
                    objective="quantile", alpha=quantile, **params
                ).fit(x[~test], y[~test])
                predictions[target][test, j] = model.predict(x[test])
                # Baselines: the previous in-match-only features, and one
                # constant quantile for every situation.
                base = lgb.LGBMRegressor(
                    objective="quantile", alpha=quantile, **params
                ).fit(x.loc[~test, BASE_FEATURES], y[~test])
                base_predictions[target][test, j] = base.predict(
                    x.loc[test, BASE_FEATURES]
                )
                constant[target][test, j] = np.quantile(y[~test], quantile)
                if target == "xg_for" and quantile == 0.5:
                    leading, trailing = x[test].copy(), x[test].copy()
                    leading["score_diff"], trailing["score_diff"] = 1, -1
                    score_shift[test] = model.predict(leading) - model.predict(trailing)
            predictions[target][test] = bound_predictions(
                predictions[target][test], target
            )
            base_predictions[target][test] = bound_predictions(
                base_predictions[target][test], target
            )
            result = evaluate(y[test], predictions[target][test])
            fold_metrics.append({"fold": fold, "target": target, **result})
            print("Game-state", fold, target, result, flush=True)
    report = {
        "training_date": timestamp(),
        "n_matches": int(windows.game_id.nunique()),
        "n_windows": len(all_windows),
        "n_training_windows": len(windows),
        "n_censored_windows": int((~complete).sum()),
        "features": FEATURES,
        "targets": TARGETS,
        "params": params,
        "validation": (
            "5 grouped outer match folds; upstream xG/VAEP refitted excluding "
            "each held-out fold; player ratings exclude the held-out fold and "
            "each row's own match; complete 15-minute horizons only"
        ),
        "metrics": {},
        "fold_metrics": fold_metrics,
        "baselines": {},
        "calibration": {
            "method": (
                "p10/p90 distance from p50 scaled to minimise out-of-fold "
                "pinball loss; reported metrics are cross-fitted (factors "
                "fitted on the other four folds) and production uses factors "
                "fitted on all out-of-fold forecasts."
            ),
            "factors": {},
            "uncalibrated": {},
        },
    }
    scored = windows[
        [
            "match_id",
            "team",
            "minute",
            "period",
            "score_diff",
            "players_for",
            "players_against",
        ]
    ].copy()
    for target in TARGETS:
        y, raw = outcomes[target], predictions[target]
        report["calibration"]["uncalibrated"][target] = evaluate(y, raw)
        p = raw.copy()
        for fold in range(5):
            test = folds == fold
            p[test] = calibrate(
                raw[test], target, fit_factors(y[~test], raw[~test], target)
            )
        report["calibration"]["factors"][target] = fit_factors(y, raw, target)
        predictions[target] = p
        report["baselines"][target] = {
            "in_match_only": evaluate(y, base_predictions[target]),
            "constant": evaluate(y, constant[target]),
        }
        report["metrics"][target] = evaluate(y, p)
        report["metrics"][target]["by_state"] = {}
        for state, select in {
            "leading": windows.score_diff.to_numpy() > 0,
            "drawing": windows.score_diff.to_numpy() == 0,
            "trailing": windows.score_diff.to_numpy() < 0,
            "red_card": (windows.players_for.to_numpy() < 11)
            | (windows.players_against.to_numpy() < 11),
            "early": windows.minute.to_numpy() < 30,
            "late": windows.minute.to_numpy() >= 60,
        }.items():
            if select.any():
                report["metrics"][target]["by_state"][state] = evaluate(
                    y[select], p[select]
                )
        scored[f"outcome_{target}"] = y
        for j, q in enumerate([10, 50, 90]):
            scored[f"{target}_p{q}"] = p[:, j]
    lead, trail = windows.score_diff.to_numpy() > 0, windows.score_diff.to_numpy() < 0
    report["confounding_diagnostic"] = {
        "definition": (
            "Only score_diff changed from -1 to +1, holding all other held-out "
            "features fixed; compare median prediction sensitivity with raw "
            "mean outcome association (different estimands, neither causal)."
        ),
        "mean_modelled_median_xg_shift": float(score_shift.mean()),
        "raw_mean_xg_leading": float(outcomes["xg_for"][lead].mean()),
        "raw_mean_xg_trailing": float(outcomes["xg_for"][trail].mean()),
        "raw_mean_xg_difference": float(
            outcomes["xg_for"][lead].mean() - outcomes["xg_for"][trail].mean()
        ),
    }
    scored.to_parquet(data_dir() / "processed/gamestate_oof.parquet", index=False)
    x = featurize(windows)
    for target in TARGETS:
        for quantile in QUANTILES:
            model = lgb.LGBMRegressor(
                objective="quantile", alpha=quantile, **params
            ).fit(x, windows[f"outcome_{target}"])
            model.booster_.save_model(
                str(
                    data_dir() / f"models/gamestate_{target}_p{int(quantile * 100)}.txt"
                )
            )
    save_json("gamestate.json", report)
    print(json.dumps(report["metrics"], indent=2), flush=True)


if __name__ == "__main__":
    main()
