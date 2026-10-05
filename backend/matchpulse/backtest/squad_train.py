"""W12 candidate fits; frozen splits and explicit keep-the-better-model gates."""

import json
from datetime import UTC, datetime

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.special import softmax

from matchpulse.backtest.common import output, root, save
from matchpulse.backtest.inplay import calibrated
from matchpulse.backtest.statistics import scores
from matchpulse.models.squad import LIVE_FEATURES, SQUAD_FEATURES

BEFORE = "w10-frozen-2015-xg-vaep-v1"
AFTER = "w12-historical-squads-v1"


def offset_predict(
    x: np.ndarray,
    y: np.ndarray,
    base: np.ndarray,
    target: np.ndarray,
    target_base: np.ndarray,
    penalty: float,
) -> np.ndarray:
    """Fit a regularized correction to rating logits using preceding rounds only."""
    with np.errstate(invalid="ignore"):
        medians = np.array(
            [np.nanmedian(v) if np.isfinite(v).any() else 0 for v in x.T]
        )
    x = np.where(np.isfinite(x), x, medians)
    target = np.where(np.isfinite(target), target, medians)
    scale = np.std(x, axis=0)
    scale[scale < 1e-6] = 1
    x, target = (x - medians) / scale, (target - medians) / scale
    x, target = np.clip(x, -5, 5), np.clip(target, -5, 5)
    # No intercept: preserve the base model's priors when squad evidence is absent.
    labels = np.eye(3)[y]
    logits = np.log(np.clip(base, 1e-9, 1))

    def objective(flat: np.ndarray) -> tuple[float, np.ndarray]:
        w = flat.reshape(x.shape[1], 3)
        probabilities = softmax(logits + x @ w, axis=1)
        loss = (
            -np.sum(labels * np.log(np.clip(probabilities, 1e-12, 1)))
            + penalty * np.sum(w * w) / 2
        )
        grad = x.T @ (probabilities - labels) + penalty * w
        return float(loss), grad.ravel()

    fitted = minimize(objective, np.zeros(x.shape[1] * 3), jac=True, method="L-BFGS-B")
    if not fitted.success:
        raise RuntimeError(f"Offset optimizer failed: {fitted.message}")
    return softmax(
        np.log(np.clip(target_base, 1e-9, 1))
        + target @ fitted.x.reshape(x.shape[1], 3),
        axis=1,
    )


def prematch() -> dict:
    before = output() / "w12_before"
    rows = json.loads((before / "prematch_predictions.json").read_text())
    selection = json.loads((before / "prematch_selection.json").read_text())
    frame = pd.DataFrame(rows).merge(
        pd.read_parquet(output() / "squad_prematch.parquet"),
        on="match_id",
        validate="one_to_one",
        sort=False,
    )
    base = np.array([r["model"] for r in rows])
    y = np.array([r["result"] for r in rows])
    tune = frame["round"].between(6, 17).to_numpy()
    evaluation = (frame["round"] >= 18).to_numpy()
    feature_sets = {
        "value": [
            "xi_log_total_diff",
            "xi_log_total_level",
            "xi_mean_log_diff",
            "bench_log_total_diff",
        ],
        "value_age": [
            "xi_log_total_diff",
            "xi_log_total_level",
            "bench_log_total_diff",
            "mean_age_diff",
            "mean_age_level",
        ],
        "all": SQUAD_FEATURES,
    }
    candidates, probabilities = [], []
    for name, features in feature_sets.items():
        for penalty in (10.0, 100.0):
            p = base.copy()
            x = frame[features].to_numpy(dtype=float)
            for week in range(6, 35):
                historical = (frame["round"] < min(week, 18)).to_numpy()
                target = (frame["round"] == week).to_numpy()
                p[target] = offset_predict(
                    x[historical],
                    y[historical],
                    base[historical],
                    x[target],
                    base[target],
                    penalty,
                )
            candidate = {
                "feature_set": name,
                "features": features,
                "penalty": penalty,
                **scores(y[tune], p[tune]),
            }
            candidates.append(candidate)
            probabilities.append(p)
    best_index = min(range(len(candidates)), key=lambda i: candidates[i]["log_loss"])
    best, p = candidates[best_index], probabilities[best_index]
    before_metrics, candidate_metrics = (
        scores(y[evaluation], base[evaluation]),
        scores(y[evaluation], p[evaluation]),
    )
    accepted = (
        all(candidate_metrics[k] < before_metrics[k] for k in ("log_loss", "brier"))
        and best["log_loss"] < scores(y[tune], base[tune])["log_loss"]
    )
    thresholds = []
    for threshold in (0.0, 0.05, 0.1, 0.2):
        bets = [
            (i, k)
            for i, row in enumerate(rows)
            if tune[i]
            for k in range(3)
            if p[i, k] * row["closing"][k] - 1 > threshold
        ]
        thresholds.append(
            {
                "threshold": threshold,
                "n_bets": len(bets),
                "pnl": sum(
                    (rows[i]["closing"][k] if y[i] == k else 0) - 1 for i, k in bets
                ),
            }
        )
    chosen_threshold = max(thresholds, key=lambda t: t["pnl"])["threshold"]
    candidate_rows = [{**r, "model": p[i].tolist()} for i, r in enumerate(rows)]
    save(output() / "squad_prematch_candidate_predictions.json", candidate_rows)
    save(
        output() / "squad_prematch_candidate_selection.json",
        {**selection, "threshold": chosen_threshold, "squad_selection": best},
    )
    save(output() / "prematch_predictions.json", candidate_rows if accepted else rows)
    save(
        output() / "prematch_selection.json",
        {
            **selection,
            "threshold": chosen_threshold if accepted else selection["threshold"],
            "squad_accepted": accepted,
            "squad_selection": best,
            "squad_candidates": candidates,
            "squad_thresholds": thresholds,
        },
    )
    market = 1 / np.array([r["closing"] for r in rows])
    report = {
        "training_date": datetime.now(UTC).isoformat(),
        "n_matches": len(rows),
        "tune_matches": int(tune.sum()),
        "evaluation_matches": int(evaluation.sum()),
        "features": feature_sets,
        "candidates": candidates,
        "selected": best,
        "before_tuning": scores(y[tune], base[tune]),
        "metrics": {
            "before": before_metrics,
            "candidate": candidate_metrics,
            "retained": candidate_metrics if accepted else before_metrics,
            "market": scores(y[evaluation], market[evaluation]),
        },
        "accepted": accepted,
        "gate": (
            "Candidate chosen on tuning only; held-out Brier AND log loss "
            "must improve to replace incumbent, as requested. "
            "Retention uses evaluation data; no candidate retuning."
        ),
        "threshold": chosen_threshold,
        "before_threshold": selection["threshold"],
    }
    save(root() / "models/backtest_squad_prematch.json", report)
    print("Pre-match", json.dumps(report["metrics"]), "accepted", accepted, flush=True)
    return report


def inplay() -> dict:
    before = output() / "w12_before"
    data = pd.read_parquet(before / "inplay_features.parquet").merge(
        pd.read_parquet(output() / "squad_live.parquet"),
        on=["match_id", "period", "minute"],
        validate="one_to_one",
    )
    old = joblib.load(before / "backtest_inplay.joblib")
    incumbent = old["model"]
    features = incumbent["features"] + LIVE_FEATURES
    train, calibration, validation, test = [
        data.split == s for s in ("train", "calibration", "validation", "backtest")
    ]
    # Fixed incumbent settings; no parameter search on validation.
    model = lgb.LGBMClassifier(**incumbent["model"].get_params())
    model.fit(data.loc[train, features], data.loc[train, "result"])

    def objective(t: float) -> float:
        return scores(
            data.loc[calibration, "result"].to_numpy(),
            calibrated(model, data.loc[calibration, features], t),
        )["log_loss"]

    temperature = float(minimize_scalar(objective, bounds=(0.5, 3), method="bounded").x)
    candidate = {"model": model, "features": features, "temperature": temperature}
    metrics = {}
    for name, mask in [("validation", validation), ("tournaments", test)]:
        metrics[name] = {}
        for label, bundle in [
            ("before", incumbent),
            ("candidate", candidate),
            ("score_only_baseline", old["baseline"]),
        ]:
            p = calibrated(
                bundle["model"],
                data.loc[mask, bundle["features"]],
                bundle["temperature"],
            )
            metrics[name][label] = scores(data.loc[mask, "result"].to_numpy(), p)
    accepted = all(
        metrics["validation"]["candidate"][k] < metrics["validation"]["before"][k]
        for k in ("log_loss", "brier")
    )
    for partition in metrics.values():
        partition["retained"] = partition["candidate" if accepted else "before"]
    active = candidate if accepted else incumbent
    bundle = {**old, "model": active}
    report = {
        **json.loads((before / "backtest_inplay.json").read_text()),
        "training_date": datetime.now(UTC).isoformat(),
        "features": active["features"],
        "squad_features": LIVE_FEATURES,
        "squad_accepted": accepted,
        "squad_metrics": metrics,
        "candidate_temperature": temperature,
        "model_version": AFTER if accepted else BEFORE,
        "selection": (
            "Fixed classifier, separate 2018-19 calibration; validation "
            "Brier AND log loss retention gate. Tournaments never select."
        ),
    }
    report["metrics"]["model"] = {
        **metrics["validation"]["retained"],
        "temperature": active["temperature"],
    }
    joblib.dump(
        {**old, "model": candidate}, root() / "models/backtest_inplay_squad.joblib"
    )
    save(
        root() / "models/backtest_inplay_squad.json",
        {
            **report,
            "features": features,
            "model_version": AFTER,
            "metrics": {
                **report["metrics"],
                "model": {
                    **metrics["validation"]["candidate"],
                    "temperature": temperature,
                },
            },
        },
    )
    joblib.dump(bundle, root() / "models/backtest_inplay.joblib")
    save(root() / "models/backtest_inplay.json", report)
    save(output() / "inplay_metrics.json", report)
    for name, predictor in [
        ("inplay_predictions.parquet", active),
        ("squad_inplay_candidate_predictions.parquet", candidate),
    ]:
        result = data.loc[test].copy()
        p = calibrated(
            predictor["model"], result[predictor["features"]], predictor["temperature"]
        )
        for k, side in enumerate(("home", "draw", "away")):
            result[f"p_{side}"] = p[:, k]
        result.to_parquet(output() / name, index=False)
    print("In-play", json.dumps(metrics), "accepted", accepted, flush=True)
    return report


def main() -> None:
    prematch()
    inplay()


if __name__ == "__main__":
    main()
