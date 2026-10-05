"""Standard socceraction three-state VAEP, cross-fitted by whole match.

Periods are separate sequences: neither histories nor ten-action labels cross
half-time. Labels include the current action, as in socceraction's definition.
Thus post-action goal results are legitimate features, not a pre-shot forecast.
"""

import argparse
import gc
import warnings
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score
from socceraction.vaep import VAEP
from socceraction.vaep.features import goalscore
from socceraction.vaep.formula import value

from matchpulse.models.common import catalogue, data_dir, fold_map, save_json, timestamp


def prepare_match(match: dict[str, Any]) -> int:
    path = data_dir() / f"processed/vaep_features/{match['native_id']}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    actions = pd.read_parquet(
        data_dir() / f"processed/spadl/{match['native_id']}.parquet"
    )
    frames = []
    vaep = VAEP(nb_prev_actions=3)
    score_context = goalscore([actions]).set_index(actions.action_id)
    for _, group in actions.groupby("period_id", sort=False):
        group = group.reset_index(drop=True)
        game = pd.Series({"home_team_id": match["home"]["id"]})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            x = vaep.compute_features(game, group).astype("float32")
            y = vaep.compute_labels(game, group)
        # Reset action history at breaks, but preserve the match score.
        for column in score_context:
            x[column] = score_context.loc[group.action_id, column].to_numpy(
                dtype="float32"
            )
        x["label_scores"] = y.scores.astype("int8")
        x["label_concedes"] = y.concedes.astype("int8")
        x["game_id"] = match["native_id"]
        x["action_id"] = group.action_id
        x["period_id"] = group.period_id
        frames.append(x)
    pd.concat(frames, ignore_index=True).to_parquet(path, index=False)
    return len(actions)


def train() -> None:
    matches = catalogue()
    import pyarrow.parquet as pq

    paths = [
        data_dir() / f"processed/vaep_features/{m['native_id']}.parquet"
        for m in matches
    ]
    sizes = [pq.read_metadata(path).num_rows for path in paths]
    excluded = ["game_id", "action_id", "period_id", "label_scores", "label_concedes"]
    features = [c for c in pq.read_schema(paths[0]).names if c not in excluded]
    n = sum(sizes)
    x = np.lib.format.open_memmap(
        data_dir() / "processed/vaep_features.npy",
        mode="w+",
        dtype="float32",
        shape=(n, len(features)),
    )
    game_ids, action_ids = np.empty(n, dtype="int64"), np.empty(n, dtype="int32")
    eligible = np.empty(n, dtype=bool)
    labels = {target: np.empty(n, dtype="int8") for target in ["scores", "concedes"]}
    offset = 0
    for i, (path, size) in enumerate(zip(paths, sizes, strict=True)):
        data = pd.read_parquet(path)
        section = slice(offset, offset + size)
        x[section] = data[features].to_numpy(dtype="float32")
        game_ids[section], action_ids[section] = data.game_id, data.action_id
        eligible[section] = data.period_id < 5
        for target in labels:
            labels[target][section] = data[f"label_{target}"]
        offset += size
        if i % 500 == 0:
            print("Loaded", i, flush=True)
    x.flush()
    del data
    keys = pd.DataFrame({"game_id": game_ids, "action_id": action_ids})
    fold = keys.game_id.map(fold_map()).to_numpy()
    gc.collect()
    params = dict(
        n_estimators=140,
        num_leaves=15,
        learning_rate=0.07,
        min_child_samples=250,
        max_bin=63,
        reg_lambda=5,
        n_jobs=16,
        verbosity=-1,
        random_state=2026,
        force_col_wise=True,
    )
    report = {
        "training_date": timestamp(),
        "n_matches": len(matches),
        "n_actions": len(x),
        "n_training_actions": int(eligible.sum()),
        "features": features,
        "params": params,
        "validation": (
            "5 grouped match folds; each period independent; "
            "shootouts predicted but excluded from training/evaluation"
        ),
        "metrics": {},
    }
    for target, y in labels.items():
        prediction = np.zeros(len(x), dtype=np.float32)
        folds = []
        for f in range(5):
            test = fold == f
            model = lgb.LGBMClassifier(**params).fit(
                x[~test & eligible], y[~test & eligible]
            )
            prediction[test] = model.predict_proba(x[test])[:, 1]
            model.booster_.save_model(
                str(data_dir() / f"models/vaep_{target}_fold_{f}.txt")
            )
            ev = test & eligible
            folds.append(
                {
                    "fold": f,
                    "auc": float(roc_auc_score(y[ev], prediction[ev])),
                    "brier": float(brier_score_loss(y[ev], prediction[ev])),
                }
            )
            print(target, folds[-1], flush=True)
            del model
            gc.collect()
        keys[f"p_{target}"] = prediction
        report["metrics"][target] = {
            "auc": float(roc_auc_score(y[eligible], prediction[eligible])),
            "brier": float(brier_score_loss(y[eligible], prediction[eligible])),
            "base_rate": float(y[eligible].mean()),
            "folds": folds,
        }
        model = lgb.LGBMClassifier(**params).fit(x[eligible], y[eligible])
        model.booster_.save_model(str(data_dir() / f"models/vaep_{target}.txt"))
        del model
        gc.collect()
    keys["fold"] = fold
    keys.to_parquet(data_dir() / "processed/vaep_predictions.parquet", index=False)
    outdir = data_dir() / "processed/vaep"
    outdir.mkdir(exist_ok=True)
    for native, predictions in keys.groupby("game_id", sort=False):
        actions = pd.read_parquet(data_dir() / f"processed/spadl/{native}.parquet")
        actions = actions.merge(
            predictions, on=["game_id", "action_id"], validate="one_to_one"
        )
        result = []
        for _, period in actions.groupby("period_id", sort=False):
            period = period.reset_index(drop=True)
            values = value(period, period.p_scores, period.p_concedes)
            result.append(pd.concat([period, values], axis=1))
        pd.concat(result, ignore_index=True).to_parquet(
            outdir / f"{native}.parquet", index=False
        )
    save_json("vaep.json", report)
    print(report["metrics"], flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--train-only", action="store_true")
    args = parser.parse_args()
    if not args.train_only:
        with ProcessPoolExecutor(max_workers=16) as pool:
            for i, _ in enumerate(pool.map(prepare_match, catalogue()), 1):
                if i % 100 == 0:
                    print("Prepared", i, flush=True)
    if not args.prepare_only:
        train()


if __name__ == "__main__":
    main()
