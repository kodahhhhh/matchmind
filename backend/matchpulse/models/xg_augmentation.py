"""Fixed StatsBomb + W13 Dynasty xG experiment, with a source holdout.

No downloads. Only accepted normalized W13 files are read. Unknown context stays
missing exactly as in W13 inference, rather than fabricated negative indicators.
"""

import argparse
import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from matchpulse.models.common import data_dir, fold_map, timestamp
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import compare, file_hash, freeze_manifest
from matchpulse.models.xg import CATEGORIES, FEATURES, shot_features

MISSING_CONTEXT = [
    "first_time",
    "under_pressure",
    "through_ball",
    "cross",
    "cut_back",
    "opponents_in_cone",
    "keeper_present",
    "technique",
]


def extract(meta: dict, events: list[dict]) -> list[dict]:
    """Build actual-goal labels and only information observed before each shot."""
    score = {meta[side]["id"]: 0 for side in ("home", "away")}
    rows = []
    for event in events:
        if event["period"] >= 5:
            continue
        team = event["team"]["id"]
        other = next(t for t in score if t != team)
        if event["type"]["name"] == "Shot" and event.get("location"):
            row = shot_features(event)
            row["score_diff"] = score[team] - score[other]
            for column in MISSING_CONTEXT:
                row[column] = np.nan
            if event["shot"].get("body_part", {}).get("name") == "Other":
                row["body_part"] = np.nan
            if event["shot"].get("type", {}).get("name") == "Other":
                row["shot_type"] = np.nan
                row["set_piece"] = np.nan
            row["goal"] = int(event["shot"]["outcome"]["name"] == "Goal")
            row["match_id"] = meta["match_id"]
            row["original_event_id"] = event["id"]
            rows.append(row)
            score[team] += row["goal"]
        elif event["type"]["name"] == "Own Goal Against":
            score[other] += 1
    return rows


def run(out: Path) -> dict:
    """Single predeclared unit-weight augmentation; no weight/feature search."""
    root = data_dir()
    source_catalogue = root / "sources/catalogue_dynasty.json"
    matches = json.loads(source_catalogue.read_text())
    files = [
        root / f"sources/dynasty/normalized/{m['native_id']}.json" for m in matches
    ]
    shot_path = root / "processed/xg/shots.parquet"
    card = json.loads((root / "models/xg.json").read_text())
    params = {**card["params"], "n_jobs": 8}
    # Selection depends only on source match identity, never outcomes.
    ids = sorted(
        [m["match_id"] for m in matches],
        key=lambda s: hashlib.sha256(s.encode()).hexdigest(),
    )
    heldout = set(ids[::5])
    freeze_manifest(
        out / "split.json",
        {
            "protocol": "StatsBomb match folds; fixed unit-weight source augmentation",
            "params": params,
            "source_holdout_ids": sorted(heldout),
            "source_train_ids": sorted(set(ids) - heldout),
            "inputs": {
                str(p.relative_to(root)): file_hash(p)
                for p in [
                    source_catalogue,
                    shot_path,
                    root / "models/xg.json",
                    root / "models/xg.txt",
                    *(root / f"models/xg_fold_{f}.txt" for f in range(5)),
                    *files,
                ]
            },
            "statsbomb_folds": fold_map(),
            "missing_context": MISSING_CONTEXT,
        },
    )
    if (out / "xg.json").exists():
        raise ValueError("Completed experiment exists")
    rows = []
    for path in files:
        normalized = json.loads(path.read_text())
        rows.extend(extract(normalized["meta"], normalized["events"]))
    source = pd.DataFrame(rows)
    source.to_parquet(out / "source_shots.parquet", index=False)
    new = source[~source.match_id.isin(heldout)]
    test_source = source[source.match_id.isin(heldout)]
    shots = pd.read_parquet(shot_path)
    eligible = shots.period < 5
    folds = shots.game_id.map(fold_map()).to_numpy()
    p, q = np.zeros(len(shots)), np.zeros(len(shots))
    for f in range(5):
        test = folds == f
        train = ~test & eligible.to_numpy()
        x = pd.concat([shots.loc[train, FEATURES], new[FEATURES]], ignore_index=True)
        y = pd.concat([shots.loc[train, "goal"], new.goal], ignore_index=True)
        model = lgb.LGBMClassifier(**params).fit(x, y)
        q[test] = model.predict_proba(shots.loc[test, FEATURES])[:, 1]
        model.booster_.save_model(str(out / f"xg_fold_{f}.txt"))
        baseline = lgb.Booster(model_file=str(root / f"models/xg_fold_{f}.txt"))
        p[test] = baseline.predict(shots.loc[test, FEATURES], num_threads=8)
        print("Augmented xG fold", f, flush=True)
    final = lgb.LGBMClassifier(**params).fit(
        pd.concat([shots.loc[eligible, FEATURES], new[FEATURES]], ignore_index=True),
        pd.concat([shots.loc[eligible, "goal"], new.goal], ignore_index=True),
    )
    final.booster_.save_model(str(out / "xg.txt"))
    baseline = lgb.Booster(model_file=str(root / "models/xg.txt"))
    result = {
        "training_date": timestamp(),
        "n_matches": int(shots.game_id.nunique()),
        "n_shots": int(eligible.sum()),
        "n_extra_training_matches": int(new.match_id.nunique()),
        "n_extra_training_shots": len(new),
        "n_source_holdout_matches": int(test_source.match_id.nunique()),
        "n_source_holdout_shots": len(test_source),
        "features": FEATURES,
        "categories": CATEGORIES,
        "params": params,
        "validation": "StatsBomb folds; source identity-hash holdout; fixed weight 1",
        **compare(
            shots.loc[eligible, "goal"].to_numpy(),
            p[eligible],
            q[eligible],
            shots.loc[eligible, "game_id"].to_numpy(),
        ),
        "source_holdout": compare(
            test_source.goal.to_numpy(),
            baseline.predict(test_source[FEATURES], num_threads=8),
            final.predict_proba(test_source[FEATURES])[:, 1],
            test_source.match_id.to_numpy(),
        ),
        "promotion_recommended": False,
        "source_limit": (
            "Small Nigerian youth cohort with missing context; "
            "transfer is not established by adult validation"
        ),
    }
    shots["baseline_xg"], shots["xg"] = p, q
    shots.to_parquet(out / "shots.parquet", index=False)
    write_report(out / "xg.json", result)
    print(
        json.dumps(
            {
                "paired_ci": result["paired_ci"],
                "source_holdout": result["source_holdout"]["paired_ci"],
            },
            indent=2,
        )
    )
    return result


def main() -> None:
    """Test newly landed W13 data without modifying source or current artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="xg-dynasty-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
