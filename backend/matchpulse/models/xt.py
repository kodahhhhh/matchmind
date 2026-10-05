"""Match-cross-fitted 12 x 8 socceraction expected threat for successful moves."""

import numpy as np
import pandas as pd
from socceraction.spadl import play_left_to_right
from socceraction.xthreat import ExpectedThreat

from matchpulse.models.common import catalogue, data_dir, fold_map, save_json, timestamp


def main() -> None:
    frames = []
    for match in catalogue():
        actions = pd.read_parquet(
            data_dir() / f"processed/spadl/{match['native_id']}.parquet"
        )
        frames.append(play_left_to_right(actions, match["home"]["id"]))
    actions = pd.concat(frames, ignore_index=True)
    folds = actions.game_id.map(fold_map()).to_numpy()
    eligible = actions.period_id.to_numpy() < 5
    ratings = np.full(len(actions), np.nan)
    grids = []
    for fold in range(5):
        model = ExpectedThreat(l=12, w=8).fit(actions[(folds != fold) & eligible])
        test = folds == fold
        ratings[test] = model.rate(actions[test])
        grids.append(model.xT.tolist())
        print("xT fold", fold, flush=True)
    result = actions[["game_id", "action_id", "original_event_id"]].copy()
    result["xt"] = ratings
    out = data_dir() / "processed/xt"
    out.mkdir(exist_ok=True)
    for native, group in result.groupby("game_id", sort=False):
        group.to_parquet(out / f"{native}.parquet", index=False)
    model = ExpectedThreat(l=12, w=8).fit(actions[eligible])
    save_json(
        "xt.json",
        {
            "training_date": timestamp(),
            "n_matches": int(actions.game_id.nunique()),
            "n_actions": int(eligible.sum()),
            "n_rated_moves": int(np.isfinite(ratings).sum()),
            "grid_shape": [8, 12],
            "grid": model.xT.tolist(),
            "fold_grids": grids,
            "validation": (
                "5 grouped match folds; successful move end minus start; "
                "non-moves NULL; shootouts excluded from fitting"
            ),
        },
    )


if __name__ == "__main__":
    main()
