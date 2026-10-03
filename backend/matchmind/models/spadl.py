"""Convert catalogue matches locally, never consulting the incomplete match index.

Run: DATA_DIR=... uv run --group models python -m matchmind.models.spadl
Stored socceraction coordinates have the home team attacking +x in each period;
use play_left_to_right before fitting team-relative spatial models. This differs
from the raw DB's acting-team coordinates and does not replace the raw loader.
"""

import argparse
import warnings
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pandas as pd
from socceraction.data.statsbomb import StatsBombLoader
from socceraction.spadl import add_names
from socceraction.spadl.statsbomb import convert_to_actions

from matchmind.models.common import catalogue, data_dir, save_json, timestamp


def convert_match(match: dict[str, Any]) -> dict[str, Any]:
    native = match["native_id"]
    try:
        loader = StatsBombLoader(
            getter="local", root=str(data_dir() / "raw/statsbomb/data")
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            actions = add_names(
                convert_to_actions(loader.events(native), match["home"]["id"])
            )
        actions["home_team_id"] = match["home"]["id"]
        path = data_dir() / f"processed/spadl/{native}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        actions.to_parquet(path, index=False)
        return {"game_id": native, "n_actions": len(actions), "error": None}
    except Exception as exc:
        return {"game_id": native, "n_actions": 0, "error": repr(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--match-id", type=int)
    args = parser.parse_args()
    matches = [
        m
        for m in catalogue()
        if args.match_id is None or m["native_id"] == args.match_id
    ]
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, row in enumerate(pool.map(convert_match, matches), 1):
            rows.append(row)
            if i % 100 == 0 or row["error"]:
                print(i, row, flush=True)
    frame = pd.DataFrame(rows)
    frame.to_parquet(data_dir() / "processed/spadl/_index.parquet", index=False)
    report = {
        "training_date": timestamp(),
        "n_matches": len(frame),
        "n_actions": int(frame.n_actions.sum()),
        "failures": frame[frame.error.notna()].to_dict("records"),
    }
    save_json("spadl.json", report)
    print(report, flush=True)
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
