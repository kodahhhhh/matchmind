"""Evaluate xT's generative transition model and a fixed lateral-symmetry prior.

The proper-score target is next eligible action outcome (successful destination,
failed move, missed shot, goal), not causal player value or final match result.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from socceraction.spadl import play_left_to_right

from matchpulse.models.common import catalogue, data_dir, fold_map, timestamp
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import file_hash, freeze_manifest, paired_bootstrap

CELLS = 96
MIRROR = np.arange(CELLS).reshape(8, 12)[::-1].ravel()
OUTCOME_MIRROR = np.r_[MIRROR, 96, 97, 98]


def cells(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """socceraction flat grid index, including its top-to-bottom matrix layout."""
    ix = np.clip((x / 105 * 12).astype(int), 0, 11)
    iy = np.clip((y / 68 * 8).astype(int), 0, 7)
    return (7 - iy) * 12 + ix


def transition_counts(actions: pd.DataFrame) -> np.ndarray:
    """Sufficient statistics for the exact incumbent shot/move Markov model."""
    a = actions[
        (actions.period_id < 5)
        & actions.type_name.isin(["pass", "cross", "dribble", "shot"])
    ]
    start, end = (
        cells(a.start_x.to_numpy(), a.start_y.to_numpy()),
        cells(a.end_x.to_numpy(), a.end_y.to_numpy()),
    )
    success, shot = (
        (a.result_name == "success").to_numpy(),
        (a.type_name == "shot").to_numpy(),
    )
    outcome = np.where(shot, np.where(success, 98, 97), np.where(success, end, 96))
    return np.bincount(start * 99 + outcome, minlength=96 * 99).reshape(96, 99)


def transition_probabilities(counts: np.ndarray, symmetric: bool) -> np.ndarray:
    """Optional fixed reflection pools corresponding rows and destination cells."""
    if symmetric:
        counts = counts + counts[MIRROR][:, OUTCOME_MIRROR]
    totals = counts.sum(axis=1, keepdims=True)
    if (totals == 0).any():
        raise ValueError("Training has an unobserved xT cell")
    return counts / totals


def solve(probabilities: np.ndarray) -> np.ndarray:
    """Same Bellman iteration and stopping threshold as socceraction xT."""
    values = np.zeros(96)
    for _ in range(10000):
        updated = probabilities[:, 98] + probabilities[:, :96] @ values
        if np.all(updated - values <= 1e-5):
            return updated.reshape(8, 12)
        values = updated
    raise ValueError("xT iteration did not converge")


def score(counts: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    """Action-weighted proper scores, computed directly from match counts."""
    n = counts.sum()
    return {
        "log_loss": float(
            -(counts * np.log(np.clip(probabilities, 1e-15, 1))).sum() / n
        ),
        "brier": float(
            (counts.sum(axis=1) * (probabilities**2).sum(axis=1)).sum() / n
            + 1
            - 2 * (counts * probabilities).sum() / n
        ),
    }


def run(out: Path) -> dict:
    """Reproduce incumbent fold grids, score transitions and write a candidate."""
    root, matches, assignment = data_dir(), catalogue(), fold_map()
    card_path = root / "models/xt.json"
    card = json.loads(card_path.read_text())
    paths = [root / f"processed/spadl/{m['native_id']}.parquet" for m in matches]
    freeze_manifest(
        out / "split.json",
        {
            "protocol": "original five folds; fixed lateral reflection; no tuning",
            "inputs": {
                str(p.relative_to(root)): file_hash(p) for p in [card_path, *paths]
            },
            "fold_map": {str(k): v for k, v in assignment.items()},
            "metric": "99-class next eligible action outcome, not causal value",
        },
    )
    if (out / "xt.json").exists():
        raise ValueError("Completed experiment exists")
    counts = []
    for m, path in zip(matches, paths, strict=True):
        a = play_left_to_right(pd.read_parquet(path), m["home"]["id"])
        counts.append(transition_counts(a))
    counts = np.asarray(counts)
    folds = np.array([assignment[m["native_id"]] for m in matches])
    totals = counts.sum(axis=0)
    metrics = {
        name: {k: np.empty(len(matches)) for k in ("brier", "log_loss")}
        for name in ("current", "candidate")
    }
    grids, grid_errors = [], []
    for f in range(5):
        train = totals - counts[folds == f].sum(axis=0)
        p, q = (
            transition_probabilities(train, False),
            transition_probabilities(train, True),
        )
        original, new = solve(p), solve(q)
        grid_errors.append(
            float(np.max(np.abs(original - np.array(card["fold_grids"][f]))))
        )
        if grid_errors[-1] > 1e-10:
            raise ValueError("Incumbent xT reconstruction drift")
        grids.append(new.tolist())
        for i in np.flatnonzero(folds == f):
            for name, prob in (("current", p), ("candidate", q)):
                for metric, v in score(counts[i], prob).items():
                    metrics[name][metric][i] = v
    weights = counts.sum(axis=(1, 2))
    groups = np.array([m["native_id"] for m in matches])
    result = {
        "training_date": timestamp(),
        "n_matches": len(matches),
        "n_actions": int(weights.sum()),
        "grid_shape": [8, 12],
        "grid": solve(transition_probabilities(totals, True)).tolist(),
        "fold_grids": grids,
        "validation": "grouped match folds; next-action generative scores",
        "baseline_metrics": {
            k: float(np.average(v, weights=weights))
            for k, v in metrics["current"].items()
        },
        "metrics": {
            k: float(np.average(v, weights=weights))
            for k, v in metrics["candidate"].items()
        },
        "paired_ci": {
            k: paired_bootstrap(
                groups, metrics["current"][k], metrics["candidate"][k], weights=weights
            )
            for k in ("brier", "log_loss")
        },
        "incumbent_grid_max_error": max(grid_errors),
        "promotion_recommended": False,
    }
    # Ranking checks and compatible per-action OOF values, including shootouts.
    (out / "xt").mkdir(exist_ok=True)
    player_totals = []
    for m, path in zip(matches, paths, strict=True):
        a = play_left_to_right(pd.read_parquet(path), m["home"]["id"])
        f = assignment[m["native_id"]]
        start, end = (
            cells(a.start_x.to_numpy(), a.start_y.to_numpy()),
            cells(a.end_x.to_numpy(), a.end_y.to_numpy()),
        )
        ok = a.type_name.isin(["pass", "dribble", "cross"]) & (
            a.result_name == "success"
        )
        new = np.array(grids[f]).ravel()
        old = np.array(card["fold_grids"][f]).ravel()
        a["xt"] = np.where(ok, new[end] - new[start], np.nan)
        a["baseline_xt"] = np.where(ok, old[end] - old[start], np.nan)
        a[["game_id", "action_id", "original_event_id", "xt"]].to_parquet(
            out / f"xt/{m['native_id']}.parquet", index=False
        )
        player_totals.append(
            a[(a.period_id < 5) & ok].groupby("player_id")[["xt", "baseline_xt"]].sum()
        )
    players = pd.concat(player_totals).groupby(level=0).sum()
    minutes = (
        pd.read_parquet(root / "processed/player_match_vaep.parquet")
        .groupby("player_id")
        .agg(minutes=("minutes", "sum"), name=("name", "last"))
    )
    players = players.join(minutes)
    players = players[players.minutes >= 900]
    for col in ("xt", "baseline_xt"):
        players[col + "_per90"] = players[col] * 90 / players.minutes
    top = players.nlargest(20, "xt_per90")
    result["ranking_sanity"] = {
        "spearman_per90": float(
            spearmanr(players.xt_per90, players.baseline_xt_per90).statistic
        ),
        "top20_overlap": len(
            set(top.index) & set(players.nlargest(20, "baseline_xt_per90").index)
        ),
        "top20": top.reset_index().to_dict("records"),
    }
    write_report(out / "xt.json", result)
    print(
        json.dumps(
            {
                "baseline_metrics": result["baseline_metrics"],
                "metrics": result["metrics"],
                "paired_ci": result["paired_ci"],
            },
            indent=2,
        )
    )
    return result


def main() -> None:
    """Run candidate-local xT transition comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="xt-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
