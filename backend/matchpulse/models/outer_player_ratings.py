"""Revalue training matches with the outer-fold VAEP models before aggregation.

Dropping held-out rows from globally OOF player values is insufficient: other
OOF models trained on those held-out matches. This module never uses those values.
"""

import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor

import lightgbm as lgb
import pandas as pd
import pyarrow as pa
from socceraction.vaep.formula import value

from matchpulse.models.common import data_dir, fold_map

_MODELS: dict[str, lgb.Booster] = {}
_FEATURES: list[str] = []


def _initialize(fold: int) -> None:
    global _MODELS, _FEATURES
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    _FEATURES = json.loads((data_dir() / "models/vaep.json").read_text())["features"]
    _MODELS = {
        t: lgb.Booster(model_file=str(data_dir() / f"models/vaep_{t}_fold_{fold}.txt"))
        for t in ("scores", "concedes")
    }


def _match(native: int) -> pd.DataFrame:
    features = pd.read_parquet(data_dir() / f"processed/vaep_features/{native}.parquet")
    features = features[features.period_id < 5]
    probabilities = features[["game_id", "action_id"]].copy()
    for t, model in _MODELS.items():
        probabilities[t] = model.predict(features[_FEATURES], num_threads=1)
    actions = pd.read_parquet(data_dir() / f"processed/spadl/{native}.parquet")
    actions = actions[actions.period_id < 5].merge(
        probabilities, on=["game_id", "action_id"], validate="one_to_one"
    )
    frames = []
    for _, period in actions.groupby("period_id", sort=False):
        period = period.reset_index(drop=True)
        v = value(period, period.scores, period.concedes)
        frames.append(
            pd.DataFrame({"player_id": period.player_id, "vaep": v.vaep_value})
        )
    totals = pd.concat(frames).groupby("player_id").vaep.sum().reset_index()
    totals["game_id"] = native
    return totals


def rebuild(fold: int, minutes: pd.DataFrame) -> pd.DataFrame:
    """Return training-only player values from models excluding the outer fold."""
    assignment = fold_map()
    if minutes.game_id.map(assignment).isna().any():
        raise ValueError("Player minutes include matches with no saved fold")
    kept = minutes[minutes.game_id.map(assignment) != fold].drop(columns="vaep")
    ids = sorted(kept.game_id.unique().tolist())
    if not ids:
        raise ValueError("No training player matches")
    frames = []
    with ProcessPoolExecutor(
        max_workers=4,
        initializer=_initialize,
        initargs=(fold,),
        mp_context=multiprocessing.get_context("spawn"),
    ) as pool:
        for i, frame in enumerate(pool.map(_match, ids), 1):
            frames.append(frame)
            if i % 500 == 0:
                print("Outer-safe player ratings", fold, i, flush=True)
    result = kept.merge(
        pd.concat(frames, ignore_index=True),
        on=["game_id", "player_id"],
        how="left",
        validate="one_to_one",
    )
    result["vaep"] = result.vaep.fillna(0)
    return result
