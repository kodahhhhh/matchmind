"""VAEP candidates using bounded parquet batches, never a full dense matrix."""

import argparse
import gc
import json
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from matchpulse.models.common import catalogue, data_dir, fold_map, timestamp
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import compare, file_hash, freeze_manifest

PARAMS = {
    "objective": "binary",
    "learning_rate": 0.07,
    "num_leaves": 15,
    "min_data_in_leaf": 500,
    "max_bin": 63,
    "lambda_l2": 10,
    "num_threads": 8,
    "verbosity": -1,
    "seed": 2026,
    "force_col_wise": True,
    "feature_pre_filter": False,
}
ROUNDS = 210


class ParquetSequence(lgb.Sequence):
    """Stream whole-match feature files; cache at most two matches in RAM."""

    batch_size = 4096

    def __init__(
        self, paths: list[Path], sizes: list[int], features: list[str]
    ) -> None:
        self.paths, self.features = paths, features
        self.ends = np.cumsum(sizes)
        self._load = lru_cache(maxsize=2)(self._read)

    def _read(self, index: int) -> np.ndarray:
        frame = pd.read_parquet(
            self.paths[index], columns=[*self.features, "period_id"]
        )
        return frame.loc[frame.period_id < 5, self.features].to_numpy(dtype=np.float64)

    def __len__(self) -> int:
        return int(self.ends[-1])

    def __getitem__(self, index: int | slice | list[int]) -> np.ndarray:
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            if step != 1:
                return np.stack([self[i] for i in range(start, stop, step)])
            pieces = []
            while start < stop:
                file = int(np.searchsorted(self.ends, start, side="right"))
                offset = 0 if file == 0 else self.ends[file - 1]
                end = min(stop, self.ends[file])
                pieces.append(self._load(file)[start - offset : end - offset])
                start = int(end)
            return (
                np.concatenate(pieces) if pieces else np.empty((0, len(self.features)))
            )
        if isinstance(index, list):
            return np.stack([self[i] for i in index])
        if index < 0 or index >= len(self):
            raise IndexError(index)
        file = int(np.searchsorted(self.ends, index, side="right"))
        offset = 0 if file == 0 else self.ends[file - 1]
        return self._load(file)[index - offset]

    def release(self) -> None:
        """Release cached match arrays before training/inference."""
        self._load.cache_clear()


def run(out: Path) -> dict:
    """Run a single frozen recipe and fresh incumbent fold inference."""
    root = data_dir()
    card_path = root / "models/vaep.json"
    card = json.loads(card_path.read_text())
    features = card["features"]
    matches = catalogue()
    paths = [
        root / f"processed/vaep_features/{m['native_id']}.parquet" for m in matches
    ]
    sizes, keys, hashes = [], [], {}
    for path in paths:
        frame = pd.read_parquet(
            path,
            columns=[
                "game_id",
                "action_id",
                "period_id",
                "label_scores",
                "label_concedes",
            ],
        )
        frame = frame[frame.period_id < 5]
        sizes.append(len(frame))
        keys.append(frame)
        hashes[str(path.relative_to(root))] = file_hash(path)
    rows = pd.concat(keys, ignore_index=True)
    del keys
    assignment = fold_map()
    folds = rows.game_id.map(assignment).to_numpy()
    freeze_manifest(
        out / "split.json",
        {
            "protocol": "fixed VAEP recipe, five match folds, period-5 excluded",
            "params": PARAMS,
            "rounds": ROUNDS,
            "features": features,
            "inputs": {"models/vaep.json": file_hash(card_path), **hashes},
            "fold_map": {str(k): v for k, v in assignment.items()},
        },
    )
    if (out / "vaep.json").exists():
        raise ValueError("Completed experiment exists")
    report = {
        "training_date": timestamp(),
        "n_matches": len(matches),
        "n_training_actions": len(rows),
        "features": features,
        "params": PARAMS,
        "num_boost_round": ROUNDS,
        "metrics": {},
        "baseline_metrics": {},
        "paired_ci": {},
        "validation": "fixed recipe; same whole-match folds as incumbent",
        "promotion_recommended": False,
    }
    for target in ("scores", "concedes"):
        rows[f"current_{target}"] = np.nan
        rows[f"candidate_{target}"] = np.nan
    for fold in [0, 1, 2, 3, 4, -1]:
        included = [assignment[m["native_id"]] != fold for m in matches]
        seq = ParquetSequence(
            [p for p, ok in zip(paths, included, strict=True) if ok],
            [n for n, ok in zip(sizes, included, strict=True) if ok],
            features,
        )
        train = folds != fold
        dataset = None
        for target in ("scores", "concedes"):
            artifact = out / (
                f"vaep_{target}.txt" if fold == -1 else f"vaep_{target}_fold_{fold}.txt"
            )
            if artifact.exists():
                model = lgb.Booster(model_file=str(artifact))
            else:
                y = rows.loc[train, f"label_{target}"].to_numpy()
                if dataset is None:
                    dataset = lgb.Dataset(
                        seq, label=y, feature_name=features, params=PARAMS
                    )
                    dataset.construct()
                    seq.release()
                else:
                    dataset.set_label(y)
                model = lgb.train(PARAMS, dataset, num_boost_round=ROUNDS)
                model.save_model(str(artifact))
            if fold >= 0:
                baseline_path = root / f"models/vaep_{target}_fold_{fold}.txt"
                baseline = lgb.Booster(model_file=str(baseline_path))
                for m, path in zip(matches, paths, strict=True):
                    game = m["native_id"]
                    if assignment[game] != fold:
                        continue
                    frame = pd.read_parquet(path, columns=[*features, "period_id"])
                    x = frame.loc[frame.period_id < 5, features]
                    selected = rows.game_id == game
                    rows.loc[selected, f"current_{target}"] = baseline.predict(
                        x, num_threads=8
                    )
                    rows.loc[selected, f"candidate_{target}"] = model.predict(
                        x, num_threads=8
                    )
                del baseline
            print("VAEP completed", fold, target, flush=True)
            del model
        del dataset, seq
        gc.collect()
        rows.to_parquet(out / "predictions.parquet", index=False)
    for target in ("scores", "concedes"):
        result = compare(
            rows[f"label_{target}"].to_numpy(),
            rows[f"current_{target}"].to_numpy(),
            rows[f"candidate_{target}"].to_numpy(),
            rows.game_id.to_numpy(),
        )
        for key in ("metrics", "baseline_metrics", "paired_ci"):
            report[key][target] = result[key]
    write_report(out / "vaep.json", report)
    print(json.dumps({"paired_ci": report["paired_ci"]}, indent=2), flush=True)
    return report


def main() -> None:
    """Train one candidate using at most eight model threads."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="vaep-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
