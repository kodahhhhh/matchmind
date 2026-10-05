"""Reproducible source inventory and coordinate/coverage evidence, offline only."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from matchpulse.config import get_settings
from matchpulse.players.matching import club
from matchpulse.sources.common import dedupe, normal_name, save_json
from matchpulse.sources.pipeline import inventory


def summarize(data_dir: Path) -> dict:
    """Compare exported full streams with local StatsBomb; audit lite/model rows."""
    root = data_dir / "sources"
    reference = json.loads((data_dir / "catalogue/matches.json").read_text())
    sb = []
    for match in reference:
        if match.get("demo"):
            p = data_dir / f"processed/spadl/{match['native_id']}.parquet"
            if p.exists():
                sb.append(pq.read_metadata(p).num_rows)
    frames, full_ids = [], []
    for path in sorted((root / "dynasty/spadl").glob("*.parquet")):
        frame = pd.read_parquet(path)
        frames.append(frame)
        full_ids.append(path.stem)
    full = pd.concat(frames, ignore_index=True)
    shots = full[full.type_name.str.startswith("shot")]
    attacking_x = np.where(
        shots.team_id == shots.home_team_id, shots.start_x, 105 - shots.start_x
    )
    spatial = full[["start_x", "start_y", "end_x", "end_y"]]
    invalid = (
        (~np.isfinite(spatial)).any(axis=1)
        | ~spatial.start_x.between(0, 105)
        | ~spatial.end_x.between(0, 105)
        | ~spatial.start_y.between(0, 68)
        | ~spatial.end_y.between(0, 68)
    )
    lite = {
        "matches": 0,
        "shots": 0,
        "own_xg_rows": 0,
        "own_goals_without_xg": 0,
        "invalid_coordinates": 0,
        "missing_precise_clock": 0,
        "provider_stats_matches": 0,
    }
    dates = []
    for path in (root / "understat/lite").glob("*.json"):
        document = json.loads(path.read_text())
        lite["matches"] += 1
        dates.append(document["meta"]["match_date"])
        lite["provider_stats_matches"] += int(
            document["capabilities"].get("provider_team_stats", False)
        )
        for shot in document["shots"]:
            lite["shots"] += 1
            lite["own_xg_rows"] += int(shot["xg"] is not None)
            lite["own_goals_without_xg"] += int(
                shot["result"] == "OwnGoal" and shot["xg"] is None
            )
            lite["invalid_coordinates"] += int(
                not (0 <= shot["x"] <= 105 and 0 <= shot["y"] <= 68)
            )
            lite["missing_precise_clock"] += int(
                shot["period"] is None and shot["second"] is None
            )
    generated = []
    for path in root.glob("catalogue_*.json"):
        generated.extend(json.loads(path.read_text()))
    aliases = {
        normal_name(m[side]["name"]): normal_name(club(m[side]["name"]))
        for m in reference + generated
        for side in ("home", "away")
    }
    _, duplicates = dedupe(generated, reference, aliases)
    report = {
        "inventory": inventory(data_dir),
        "statsbomb_reference": {
            "matches": len(sb),
            "actions": sum(sb),
            "mean_actions": float(np.mean(sb)),
        },
        "dynasty": {
            "matches": len(frames),
            "actions": len(full),
            "mean_actions": len(full) / len(frames),
            "min_actions": min(map(len, frames)),
            "max_actions": max(map(len, frames)),
            "columns": list(full.columns),
            "coordinate_bounds": {
                c: [float(spatial[c].min()), float(spatial[c].max())] for c in spatial
            },
            "invalid_coordinates": int(invalid.sum()),
            "shots": len(shots),
            "attacking_shot_x_median": float(np.median(attacking_x)),
            "training_files": full_ids,
        },
        "understat": {**lite, "first_date": min(dates), "last_date": max(dates)},
        "dedupe": {
            "reviewed_club_aliases": True,
            "duplicates_or_conflicts": duplicates,
        },
    }
    save_json(root / "quality_report.json", report)
    return report


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = summarize(get_settings().data_dir)
    result["dynasty"].pop("training_files")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
