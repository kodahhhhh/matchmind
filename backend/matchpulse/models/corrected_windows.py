"""Candidate-local repair of player-rating provenance in cached outer windows."""

import argparse
from pathlib import Path

import pandas as pd

from matchpulse.models.common import data_dir, fold_map
from matchpulse.models.evaluate import destination
from matchpulse.models.evaluation import file_hash, freeze_manifest
from matchpulse.models.outer_player_ratings import rebuild
from matchpulse.models.player_ratings import lineup_from_table


def run(out: Path) -> None:
    """Keep existing xG/VAEP/xT window values; repair only rating-derived features."""
    root = data_dir()
    inputs = [
        root / "processed/player_match_vaep.parquet",
        root / "processed/gamestate_windows.parquet",
    ]
    inputs += [root / f"processed/gamestate_windows_fold_{f}.parquet" for f in range(5)]
    inputs += [
        root / f"models/vaep_{t}_fold_{f}.txt"
        for t in ("scores", "concedes")
        for f in range(5)
    ]
    freeze_manifest(
        out / "inputs.json",
        {
            "protocol": "ratings recomputed from matching outer VAEP boosters",
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in inputs},
            "fold_map": {str(k): v for k, v in fold_map().items()},
        },
    )
    minutes = pd.read_parquet(inputs[0])
    for fold in [None, 0, 1, 2, 3, 4]:
        suffix = "" if fold is None else f"_fold_{fold}"
        output = out / f"gamestate_windows{suffix}.parquet"
        if output.exists():
            continue
        if fold is None:
            ratings = minutes
        else:
            cache = out / f"player_match_vaep_fold_{fold}.parquet"
            if not cache.exists():
                rebuild(fold, minutes).to_parquet(cache, index=False)
            ratings = pd.read_parquet(cache)
            if (ratings.game_id.map(fold_map()) == fold).any():
                raise ValueError("Held-out rating contributions found")
        windows = pd.read_parquet(root / f"processed/gamestate_windows{suffix}.parquet")
        corrected = lineup_from_table(
            windows, ratings, exclude_own_prior=fold is not None
        )
        for column in corrected:
            windows[column] = corrected[column]
        windows.to_parquet(output, index=False)
        print("Corrected windows saved", fold, flush=True)
    freeze_manifest(
        out / "outputs.json",
        {p.name: file_hash(p) for p in sorted(out.glob("*.parquet"))},
    )


def main() -> None:
    """Repair isolated windows, leaving the original cache unchanged."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="corrected-windows-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
