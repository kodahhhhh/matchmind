"""Explicitly labelled rescoring of historical OOF and walk-forward archives."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from matchpulse.models.common import data_dir, timestamp
from matchpulse.models.evaluate import write_report
from matchpulse.models.evaluation import (
    compare,
    file_hash,
    freeze_manifest,
    probability_metrics,
    quantile_metrics,
)


def gamestate(out: Path) -> dict[str, Any]:
    """Rescore saved outer-fold predictions; final boosters would be in-sample."""
    path = data_dir() / "processed/gamestate_oof.parquet"
    rows = pd.read_parquet(path)
    keys = ["match_id", "team", "period", "minute"]
    if rows.duplicated(keys).any():
        raise ValueError("Game-state evaluation keys are not unique")
    freeze_manifest(
        out / "gamestate_archive.json",
        {
            "sha256": file_hash(path),
            "match_ids": sorted(rows.match_id.unique()),
            "status": "rescored_archived_outer_fold_predictions_not_refitted",
        },
    )
    result = {
        "training_date": timestamp(),
        "status": "rescored_archived_outer_fold_predictions_not_refitted",
        "validation_audit": (
            "Historical only: indirect outer-fold leakage through player ratings. "
            "Use corrected-windows-v1 and gamestate-v2 for honest comparisons."
        ),
        "metrics": {},
    }
    for target in ("xg_for", "xg_against", "possession_share"):
        result["metrics"][target] = quantile_metrics(
            rows[f"outcome_{target}"].to_numpy(),
            rows[[f"{target}_p{q}" for q in (10, 50, 90)]].to_numpy(),
        )
    write_report(out / "gamestate_evaluation.json", result)
    return result


def prematch(out: Path, candidate: Path | None = None) -> dict[str, Any]:
    """Rescore current chronological predictions against the same closing market."""
    root = data_dir()
    path = root / "processed/backtest/prematch_predictions.json"
    data = pd.DataFrame(json.loads(path.read_text()))
    rows = data[data["round"] >= 18].sort_values("match_id").reset_index(drop=True)
    if rows.match_id.duplicated().any():
        raise ValueError("Duplicate pre-match keys")
    freeze_manifest(
        out / "prematch_split.json",
        {
            "sha256": file_hash(path),
            "match_ids": rows.match_id.tolist(),
            "protocol": "weeks 18-34; current retained walk-forward predictions",
        },
    )
    y, p = rows.result.to_numpy(), np.array(rows.model.tolist())
    market = 1 / np.array(rows.closing.tolist())
    market /= market.sum(axis=1, keepdims=True)
    result = {
        "training_date": timestamp(),
        "status": "rescored_saved_walk_forward_predictions",
        "current": probability_metrics(y, p),
        "market": probability_metrics(y, market),
    }
    if candidate:
        challenger = pd.DataFrame(json.loads(candidate.read_text()))
        challenger = (
            challenger[challenger["round"] >= 18]
            .sort_values("match_id")
            .reset_index(drop=True)
        )
        if not rows[["match_id", "result", "round"]].equals(
            challenger[["match_id", "result", "round"]]
        ):
            raise ValueError("Pre-match candidate cohort or outcomes differ")
        q = np.array(challenger.model.tolist())
        result["comparison"] = compare(y, p, q, rows.match_id.to_numpy())
        result["vs_market"] = compare(y, market, q, rows.match_id.to_numpy())
    write_report(out / "prematch_evaluation.json", result)
    return result
