"""Pure scoring, match-cluster uncertainty and immutable evaluation manifests."""

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score


def file_hash(path: Path) -> str:
    """Hash a file without reading a large artifact into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_manifest(path: Path, value: dict[str, Any]) -> None:
    """Refuse silent changes to the cohort or provenance of an existing run."""
    payload = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text() != payload:
            raise ValueError(f"Frozen manifest changed: {path}; use a new run name")
    else:
        with path.open("x") as handle:
            handle.write(payload)


def probabilities(y: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Validate probabilities; binary input uses the conventional binary Brier."""
    y, p = np.asarray(y), np.asarray(p, dtype=float)
    if p.ndim not in (1, 2) or len(y) != len(p) or len(y) == 0:
        raise ValueError("Empty or misaligned probability rows")
    if not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        raise ValueError("Invalid probability")
    classes = 2 if p.ndim == 1 else p.shape[1]
    if not np.isin(y, np.arange(classes)).all():
        raise ValueError("Invalid class label")
    if p.ndim == 2 and not np.allclose(p.sum(axis=1), 1, atol=1e-6):
        raise ValueError("Class probabilities must sum to one")
    return y.astype(int), p


def losses(y: np.ndarray, p: np.ndarray) -> dict[str, np.ndarray]:
    """Per-row proper scores (multiclass Brier is the sum, range 0–2)."""
    y, p = probabilities(y, p)
    if p.ndim == 1:
        q = np.clip(p, 1e-15, 1 - 1e-15)
        return {
            "brier": (p - y) ** 2,
            "log_loss": -y * np.log(q) - (1 - y) * np.log1p(-q),
        }
    return {
        "brier": ((p - np.eye(p.shape[1])[y]) ** 2).sum(axis=1),
        "log_loss": -np.log(np.clip(p[np.arange(len(y)), y], 1e-15, 1)),
    }


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict[str, Any]:
    """Fixed-width reliability bins; empty bins do not contribute to ECE."""
    indices = np.minimum((p * bins).astype(int), bins - 1)
    curve = []
    for b in range(bins):
        selected = indices == b
        if selected.any():
            curve.append(
                {
                    "bin": b,
                    "n": int(selected.sum()),
                    "predicted": float(p[selected].mean()),
                    "observed": float(y[selected].mean()),
                }
            )
    return {
        "ece": sum(r["n"] * abs(r["predicted"] - r["observed"]) for r in curve)
        / len(y),
        "curve": curve,
    }


def probability_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    """Proper scores plus classwise calibration (binary positive class only)."""
    y, p = probabilities(y, p)
    result: dict[str, Any] = {k: float(v.mean()) for k, v in losses(y, p).items()}
    result["n"] = len(y)
    if p.ndim == 1:
        result.update(calibration(y, p))
        result["auc"] = float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None
    else:
        curves = {
            str(k): calibration((y == k).astype(int), p[:, k])
            for k in range(p.shape[1])
        }
        result["ece"] = float(np.mean([c["ece"] for c in curves.values()]))
        result["calibration"] = curves
    return result


def paired_bootstrap(
    groups: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
    draws: int = 5000,
    seed: int = 2026,
    weights: np.ndarray | None = None,
) -> dict[str, Any]:
    """CI for candidate minus current, resampling complete matches with replacement.

    Preserve row weighting of the reported score, including unequal match sizes.
    Overlapping windows and opposing perspectives always remain in one cluster.
    """
    groups, baseline, candidate = map(np.asarray, (groups, baseline, candidate))
    if (
        len(groups) != len(baseline)
        or baseline.shape != candidate.shape
        or not len(groups)
    ):
        raise ValueError("Bootstrap rows must align")
    delta = candidate - baseline
    if delta.ndim != 1 or not np.isfinite(delta).all() or draws < 1:
        raise ValueError("Invalid bootstrap losses or draws")
    weights = np.ones(len(delta)) if weights is None else np.asarray(weights)
    if (
        weights.shape != delta.shape
        or not np.isfinite(weights).all()
        or (weights <= 0).any()
    ):
        raise ValueError("Bootstrap weights must be aligned, finite and positive")
    _, inverse = np.unique(groups, return_inverse=True)
    counts = np.bincount(inverse, weights=weights)
    sums = np.bincount(inverse, weights=delta * weights)
    rng, sampled = np.random.default_rng(seed), np.empty(draws)
    for start in range(0, draws, 100):
        ids = rng.integers(len(counts), size=(min(100, draws - start), len(counts)))
        sampled[start : start + len(ids)] = sums[ids].sum(axis=1) / counts[ids].sum(
            axis=1
        )
    return {
        "delta": float(np.average(delta, weights=weights)),
        "ci95": np.quantile(sampled, [0.025, 0.975]).tolist(),
        "matches": len(counts),
        "draws": draws,
        "seed": seed,
        "definition": "candidate minus baseline; paired match-cluster percentile CI",
    }


def compare(
    y: np.ndarray, current: np.ndarray, candidate: np.ndarray, groups: np.ndarray
) -> dict[str, Any]:
    """Score aligned predictions and their paired differences."""
    before, after = losses(y, current), losses(y, candidate)
    return {
        "baseline_metrics": probability_metrics(y, current),
        "metrics": probability_metrics(y, candidate),
        "paired_ci": {k: paired_bootstrap(groups, before[k], after[k]) for k in before},
    }


def quantile_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    """Pinball loss and empirical interval calibration for p10/p50/p90."""
    y, p = np.asarray(y), np.asarray(p)
    if p.shape != (len(y), 3) or not len(y) or not np.isfinite(p).all():
        raise ValueError("Invalid quantile forecasts")
    if not np.isfinite(y).all() or (np.diff(p, axis=1) < 0).any():
        raise ValueError("Invalid outcomes or crossing quantiles")
    errors = y[:, None] - p
    q = np.array([0.1, 0.5, 0.9])
    pinball = np.maximum(q * errors, (q - 1) * errors)
    return {
        "n": len(y),
        "pinball": {
            f"p{int(100 * a)}": float(pinball[:, i].mean()) for i, a in enumerate(q)
        },
        "mean_pinball": float(pinball.mean()),
        "coverage_p10_p90": float(((y >= p[:, 0]) & (y <= p[:, 2])).mean()),
        "fraction_at_or_below": {
            f"p{int(100 * a)}": float((y <= p[:, i]).mean()) for i, a in enumerate(q)
        },
        "mean_width": float((p[:, 2] - p[:, 0]).mean()),
    }
