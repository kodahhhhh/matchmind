"""Transparent probability scores, match-cluster bootstrap and accounting."""

import numpy as np
from sklearn.metrics import log_loss

OUTCOMES = ("home", "draw", "away")


def scores(y: np.ndarray, probabilities: np.ndarray) -> dict:
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-9, 1 - 1e-9)
    p = p / p.sum(axis=1, keepdims=True)
    return {
        "brier": float(np.mean(np.sum((p - np.eye(3)[y]) ** 2, axis=1))),
        "log_loss": float(log_loss(y, p, labels=[0, 1, 2])),
    }


def roi_interval(bets: list[dict], match_ids: list[str], n: int = 5000) -> list[float]:
    """Resample entire evaluation matches, including zero-bet matches."""
    if not bets:
        return [0.0, 0.0]
    totals = {mid: [0.0, 0.0] for mid in match_ids}
    for bet in bets:
        totals[bet["match_id"]][0] += bet["stake"]
        totals[bet["match_id"]][1] += bet["pnl"]
    a = np.asarray(list(totals.values()))
    rng = np.random.default_rng(2026)
    samples = a[rng.integers(0, len(a), size=(n, len(a)))].sum(axis=1)
    valid = samples[:, 0] > 0
    values = samples[valid, 1] / samples[valid, 0]
    return [float(x) for x in np.quantile(values, [0.025, 0.975])]


def summary(bets: list[dict], match_ids: list[str], equity: list[dict]) -> dict:
    staked = sum(b["stake"] for b in bets)
    pnl = sum(b["pnl"] for b in bets)
    values = np.array([e["bankroll"] for e in equity])
    return {
        "n_matches": len(match_ids),
        "n_bets": len(bets),
        "staked": staked,
        "pnl": pnl,
        "roi": pnl / staked if staked else 0.0,
        "roi_ci95": roi_interval(bets, match_ids),
        "hit_rate": sum(b["pnl"] > 0 for b in bets) / len(bets) if bets else 0.0,
        "max_drawdown": float(np.max(np.maximum.accumulate(values) - values)),
        "equity": equity,
        "bets": bets,
    }
