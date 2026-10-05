"""Frozen shot-only recipe, same StatsBomb folds and external provider audit."""

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from matchpulse.models.common import data_dir, fold_map, timestamp
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import (
    compare,
    file_hash,
    freeze_manifest,
    probability_metrics,
)
from matchpulse.models.lite_data import read_source, source_files
from matchpulse.models.xg import FEATURES as FULL_FEATURES
from matchpulse.models.xg import shot_features
from matchpulse.models.xg_shot import FEATURES, features, predict, statsbomb_features


def legacy_predictions(shots: pd.DataFrame) -> np.ndarray:
    """Reproduce W13's current missing-context adapter from its saved full model."""
    rows = []
    for shot in shots.to_dict("records"):
        body = {
            "Head": "Head",
            "Header": "Head",
            "RightFoot": "Right Foot",
            "LeftFoot": "Left Foot",
        }.get(shot["body_part"], "Other")
        kind = {
            "Penalty": "Penalty",
            "DirectFreekick": "Free Kick",
            "FromCorner": "Corner",
            "OpenPlay": "Open Play",
        }.get(shot["situation"], "Other")
        row = shot_features(
            {
                "location": [shot["x"] * 120 / 105, (68 - shot["y"]) * 80 / 68],
                "minute": shot["minute"],
                "shot": {"body_part": {"name": body}, "type": {"name": kind}},
            }
        )
        for c in [
            "score_diff",
            "first_time",
            "under_pressure",
            "through_ball",
            "cross",
            "cut_back",
            "opponents_in_cone",
            "keeper_present",
            "technique",
        ]:
            row[c] = np.nan
        if body == "Other":
            row["body_part"] = np.nan
        if kind == "Other":
            row["shot_type"] = row["set_piece"] = np.nan
        rows.append(row)
    baseline = lgb.Booster(model_file=str(data_dir() / "models/xg.txt"))
    return baseline.predict(pd.DataFrame(rows)[FULL_FEATURES], num_threads=8)


def source_audit(model: lgb.Booster, out: Path, files: dict[str, list[Path]]) -> dict:
    """External actual-goal scoring; provider predictions are reference only."""
    result = {}
    for source, paths in files.items():
        if not paths:
            result[source] = {"status": "no local snapshots"}
            continue
        matches, shots = read_source(source, paths)
        shots["legacy_xg"] = shots.get("xg", np.nan)
        shots["xg"] = predict(shots, model)
        eligible = shots.xg.notna()
        scored = shots[eligible].copy()
        scored["goal"] = (scored.result == "Goal").astype(int)
        reference = scored.provider_xg.notna()
        audit = {
            "n_matches": len(matches),
            "n_shots": len(scored),
            "actual_goal_metrics": probability_metrics(
                scored.goal.to_numpy(), scored.xg.to_numpy()
            ),
            "provider_reference": probability_metrics(
                scored.loc[reference, "goal"].to_numpy(),
                scored.loc[reference, "provider_xg"].to_numpy(),
            ),
            "provider_mean_absolute_difference": float(
                (scored.loc[reference, "xg"] - scored.loc[reference, "provider_xg"])
                .abs()
                .mean()
            ),
            "provider_correlation": float(
                scored.loc[reference, ["xg", "provider_xg"]].corr().iloc[0, 1]
            ),
            "feature_missing_counts": features(scored).isna().sum().to_dict(),
            "competition": {},
            "limit": (
                "Provider overlap unknown; reference, never target. No source fitting."
            ),
        }
        for competition, g in scored.groupby("competition"):
            audit["competition"][competition] = {
                "n_matches": int(g.match_id.nunique()),
                "shots": len(g),
                "goals": int(g.goal.sum()),
                "own_xg": float(g.xg.sum()),
                "provider_xg": float(g.provider_xg.sum()),
                "metrics": probability_metrics(g.goal.to_numpy(), g.xg.to_numpy()),
            }
        if scored.legacy_xg.notna().all():
            legacy = legacy_predictions(scored)
            audit["legacy_replay_max_error"] = float(
                np.max(np.abs(legacy - scored.legacy_xg.to_numpy()))
            )
            audit["vs_legacy_missing_context"] = compare(
                scored.goal.to_numpy(),
                legacy,
                scored.xg.to_numpy(),
                scored.match_id.to_numpy(),
            )
        shots.to_parquet(out / f"{source}_shots.parquet", index=False)
        matches.to_parquet(out / f"{source}_matches.parquet", index=False)
        result[source] = audit
    return result


def run(out: Path) -> dict:
    """Train only on StatsBomb actual-goal labels, with frozen match folds."""
    root = data_dir()
    path = root / "processed/xg/shots.parquet"
    current = json.loads((root / "models/xg.json").read_text())
    params = {**current["params"], "n_jobs": 8}
    files = source_files()
    inputs = [
        path,
        root / "models/xg.json",
        *(root / f"models/xg_fold_{f}.txt" for f in range(5)),
    ]
    inputs += [p for paths in files.values() for p in paths]
    freeze_manifest(
        out / "split.json",
        {
            "protocol": (
                "fixed incumbent parameters; reduced shot features; same match folds"
            ),
            "features": FEATURES,
            "params": params,
            "folds": fold_map(),
            "source_files": {s: [str(p) for p in ps] for s, ps in files.items()},
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in inputs},
            "excluded": (
                "provider xG, outcomes, assists, clock/score without verified ordering"
            ),
        },
    )
    if (out / "xg_shot.json").exists():
        raise ValueError("Completed candidate exists")
    shots = pd.read_parquet(path)
    shots = shots[shots.period < 5].copy().reset_index(drop=True)
    x, y = statsbomb_features(shots), shots.goal.to_numpy()
    folds = shots.game_id.map(fold_map()).to_numpy()
    p, q = np.zeros(len(shots)), np.zeros(len(shots))
    for f in range(5):
        test = folds == f
        model = lgb.LGBMClassifier(**params).fit(
            x[~test], y[~test], categorical_feature=["body_part", "situation"]
        )
        model.booster_.save_model(str(out / f"xg_shot_fold_{f}.txt"))
        q[test] = model.predict_proba(x[test])[:, 1]
        baseline = lgb.Booster(model_file=str(root / f"models/xg_fold_{f}.txt"))
        p[test] = baseline.predict(shots.loc[test, FULL_FEATURES], num_threads=8)
        print("Shot-only xG fold", f, flush=True)
    final = lgb.LGBMClassifier(**params).fit(
        x, y, categorical_feature=["body_part", "situation"]
    )
    final.booster_.save_model(str(out / "xg_shot.txt"))
    shots["full_xg"], shots["xg"] = p, q
    shots.to_parquet(out / "shots.parquet", index=False)
    report = {
        "training_date": timestamp(),
        "n_matches": int(shots.game_id.nunique()),
        "n_shots": len(shots),
        "features": FEATURES,
        "params": params,
        "validation": "five match folds; no test tuning or calibration",
        **compare(y, p, q, shots.game_id.to_numpy()),
        "source_audit": source_audit(final.booster_, out, files),
        "promotion_recommended": False,
        "intended_use": "separate lite xG, never replace full-context xG",
    }
    write_report(out / "xg_shot.json", report)
    print(json.dumps({"paired_ci": report["paired_ci"]}, indent=2), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="xg-shot-v1")
    run(destination(parser.parse_args().run))


if __name__ == "__main__":
    main()
