"""Reproducible evaluation: read production artifacts, write candidates only."""

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from matchpulse.models.common import data_dir, fold_map, timestamp
from matchpulse.models.evaluation import file_hash, freeze_manifest, probability_metrics


def destination(name: str) -> Path:
    """Constrain run outputs to candidates, including symlink resolution."""
    base = (data_dir() / "models/candidates").resolve()
    path = (base / name).resolve()
    if path == base or not path.is_relative_to(base):
        raise ValueError("Run name must be inside models/candidates")
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_report(path: Path, report: dict[str, Any]) -> None:
    """Write JSON without nonfinite numbers."""
    path.write_text(json.dumps(report, indent=2, allow_nan=False, default=str) + "\n")


def inventory(out: Path) -> dict[str, Any]:
    """Snapshot model cards, explicitly distinguished from new evaluation."""
    names = [
        "xg",
        "vaep",
        "xt",
        "gamestate",
        "goals",
        "pass_options",
        "backtest_inplay",
        "backtest_inplay_squad",
        "backtest_squad_prematch",
        "vaep_sanity",
    ]
    result = {}
    for name in names:
        path = data_dir() / f"models/{name}.json"
        result[name] = {
            "status": "historical_report_not_rerun",
            "sha256": file_hash(path),
            "card": json.loads(path.read_text()),
        }
    freeze_manifest(out / "inventory.json", result)
    return result


def inplay_data(out: Path) -> pd.DataFrame:
    """Pin the chronological feature cache and upstream fit provenance."""
    root = data_dir()
    path = root / "processed/backtest/inplay_features.parquet"
    data = pd.read_parquet(path)
    if data.duplicated(["game_id", "period", "minute"]).any():
        raise ValueError("Duplicate minute keys")
    if (data.groupby("game_id").split.nunique() != 1).any():
        raise ValueError("Match crosses chronological partitions")
    cards = [
        root / f"models/{name}.json"
        for name in ("backtest_inplay", "backtest_vaep", "backtest_prematch_xg")
    ]
    upstream = [set(json.loads(p.read_text())["training_match_ids"]) for p in cards[1:]]
    if any(set(data.game_id) & ids for ids in upstream):
        raise ValueError("Upstream training overlaps result-model data")
    original = json.loads(cards[0].read_text())["splits"]
    for split, group in data.groupby("split"):
        if sorted(group.game_id.unique().tolist()) != original[split]["match_ids"]:
            raise ValueError(f"Incumbent split changed: {split}")
    paths = [
        path,
        *cards,
        root / "catalogue/matches.json",
        root / "models/backtest_inplay.joblib",
        root / "models/backtest_vaep.joblib",
        root / "models/backtest_prematch_xg.txt",
    ]
    freeze_manifest(
        out / "split.json",
        {
            "protocol": "original chronological splits; upstream before 2015-08-01",
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in paths},
            "splits": {
                s: sorted(g.game_id.unique().tolist()) for s, g in data.groupby("split")
            },
        },
    )
    return data


def bundle_predict(bundle: dict, data: pd.DataFrame, key: str = "model") -> np.ndarray:
    """Use the existing inference contract with a bounded thread count."""
    from matchpulse.backtest.inplay import calibrated

    item = bundle[key]
    item["model"].set_params(n_jobs=8)
    return calibrated(item["model"], data[item["features"]], item["temperature"])


def inplay(out: Path, candidate: Path | None = None) -> dict[str, Any]:
    """Fresh predictions from current and optional candidate on identical rows."""
    from matchpulse.models.evaluation import compare

    data = inplay_data(out)
    current = joblib.load(data_dir() / "models/backtest_inplay.joblib")
    challenger = joblib.load(candidate) if candidate else None
    result = {
        "training_date": timestamp(),
        "status": "fresh_artifact_predictions",
        "splits": {},
    }
    for split in ("validation", "backtest"):
        rows = data[data.split == split]
        y = rows.result.to_numpy()
        p = bundle_predict(current, rows)
        naive = bundle_predict(current, rows, "baseline")
        entry = {
            "current": probability_metrics(y, p),
            "naive": probability_metrics(y, naive),
            "n_matches": int(rows.game_id.nunique()),
        }
        if challenger:
            q = bundle_predict(challenger, rows)
            entry["comparison"] = compare(y, p, q, rows.game_id.to_numpy())
            entry["vs_naive"] = compare(y, naive, q, rows.game_id.to_numpy())
        result["splits"][split] = entry
    result["market_checkpoints"] = inplay_markets(data, current, challenger, out)
    write_report(out / "inplay_evaluation.json", result)
    return result


def inplay_markets(
    data: pd.DataFrame, current: dict, candidate: dict | None, out: Path
) -> dict[str, Any]:
    """Replay cached market checkpoints with the original three-minute lag."""
    from matchpulse.models.evaluation import compare

    root = data_dir()
    records, paths = [], []
    keys = data.set_index(["match_id", "period", "minute"])
    for path in sorted((root / "processed/backtest").glob("market_sb_*.json")):
        market = json.loads(path.read_text())
        if not market["aligned"]:
            continue
        paths.append(path)
        for point in market["series"]:
            minute, period = point["minute"], point["period"]
            if minute not in (15, 30, 45, 60, 75) or (minute == 45 and period != 1):
                continue
            row = keys.loc[(market["match_id"], period, minute - 3)].to_dict()
            row.update(match_id=market["match_id"], period=period, minute=minute - 3)
            row["checkpoint"] = minute
            row["market"] = [point["market"][k] for k in ("home", "draw", "away")]
            records.append(row)
    freeze_manifest(
        out / "market_inputs.json",
        {
            "lag_minutes": 3,
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in paths},
        },
    )
    result = {}
    for minute in (15, 30, 45, 60, 75):
        rows = pd.DataFrame([r for r in records if r["checkpoint"] == minute])
        if rows.empty:
            continue
        y, groups = rows.result.to_numpy(), rows.match_id.to_numpy()
        market = np.array(rows.market.tolist())
        market /= market.sum(axis=1, keepdims=True)
        p = bundle_predict(current, rows)
        result[str(minute)] = {
            "current": probability_metrics(y, p),
            "market": probability_metrics(y, market),
            "naive": probability_metrics(y, bundle_predict(current, rows, "baseline")),
            "n_matches": int(rows.match_id.nunique()),
        }
        if candidate:
            q = bundle_predict(candidate, rows)
            result[str(minute)]["vs_current"] = compare(y, p, q, groups)
            result[str(minute)]["vs_market"] = compare(y, market, q, groups)
    return result


def xg(out: Path, candidate: Path | None = None) -> dict[str, Any]:
    """Predict using incumbent held-out fold boosters, never its all-match fit."""
    from matchpulse.models.xg import FEATURES

    root = data_dir()
    path = root / "processed/xg/shots.parquet"
    rows = pd.read_parquet(path)
    rows = rows[rows.period < 5].copy()
    paths = [path, *[root / f"models/xg_fold_{f}.txt" for f in range(5)]]
    freeze_manifest(
        out / "xg_split.json",
        {
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in paths},
            "folds": {
                str(f): sorted(g.game_id.unique().tolist())
                for f, g in rows.groupby("fold")
            },
        },
    )
    if not np.array_equal(rows.fold, rows.game_id.map(fold_map())):
        raise ValueError("xG fold assignment drift")
    p, q = np.empty(len(rows)), np.empty(len(rows))
    if candidate:
        manifest = json.loads((candidate / "split.json").read_text())
        if manifest["inputs"][str(path.relative_to(root))] != file_hash(path):
            raise ValueError("Candidate and incumbent xG data differ")
    for f in range(5):
        mask = rows.fold.to_numpy() == f
        model = lgb.Booster(model_file=str(root / f"models/xg_fold_{f}.txt"))
        p[mask] = model.predict(rows.loc[mask, FEATURES], num_threads=8)
        if candidate:
            model = lgb.Booster(model_file=str(candidate / f"xg_fold_{f}.txt"))
            q[mask] = model.predict(rows.loc[mask, FEATURES], num_threads=8)
    result = {
        "training_date": timestamp(),
        "status": "fresh_fold_artifact_predictions",
        "metrics": probability_metrics(rows.goal.to_numpy(), p),
        "statsbomb_reference": probability_metrics(
            rows.goal.to_numpy(), rows.sb_xg.to_numpy()
        ),
        "n_matches": int(rows.game_id.nunique()),
        "max_difference_from_saved_oof": float(np.max(np.abs(p - rows.xg.to_numpy()))),
    }
    if candidate:
        from matchpulse.models.evaluation import compare

        result["comparison"] = compare(
            rows.goal.to_numpy(), p, q, rows.game_id.to_numpy()
        )
    write_report(out / "xg_evaluation.json", result)
    return result


def main() -> None:
    """Dispatch safe evaluation adapters."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=["inventory", "inplay", "xg"])
    parser.add_argument("--run", default="baseline-v1")
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    out = destination(args.run)
    if args.name == "inventory":
        result = inventory(out)
        print(json.dumps({k: v["status"] for k, v in result.items()}, indent=2))
    elif args.name == "inplay":
        result = inplay(out, args.candidate)
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(xg(out, args.candidate), indent=2))


if __name__ == "__main__":
    main()
