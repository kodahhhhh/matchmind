"""Offline counts, SPADL conventions and spatial evidence for round 2."""

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from matchpulse.config import get_settings
from matchpulse.sources.common import save_json


def summarize(data_dir: Path) -> dict:
    """Audit each file independently to keep memory bounded during bulk imports."""
    root = data_dir / "sources"
    reference = next((data_dir / "processed/spadl").glob("*.parquet"))
    expected = pq.read_schema(reference).names
    report = {"full": {}, "lite": {}, "inventory": []}
    for source in ("wyscout", "dynasty", "whoscored"):
        catalogue = root / f"catalogue_{source}.json"
        if not catalogue.exists():
            continue
        matches = json.loads(catalogue.read_text())
        counts = Counter((m["competition"], m["season"]) for m in matches)
        report["inventory"].extend(
            {
                "source": source,
                "tier": "full",
                "competition": key[0],
                "season": key[1],
                "matches": value,
            }
            for key, value in sorted(counts.items())
        )
        sizes, shot_x, columns, invalid = [], [], set(), 0
        xg, vaep, xt, inferred = 0, 0, 0, 0
        for match in matches:
            p = root / f"{source}/spadl/{match['native_id']}.parquet"
            frame = pd.read_parquet(p)
            sizes.append(len(frame))
            columns.add(tuple(frame.columns))
            spatial = frame[["start_x", "start_y", "end_x", "end_y"]]
            invalid += int(
                (
                    (~np.isfinite(spatial)).any(axis=1)
                    | ~spatial.start_x.between(0, 105)
                    | ~spatial.end_x.between(0, 105)
                    | ~spatial.start_y.between(0, 68)
                    | ~spatial.end_y.between(0, 68)
                ).sum()
            )
            shots = frame[frame.type_name.str.startswith("shot")]
            shot_x.extend(
                np.where(
                    shots.team_id == shots.home_team_id,
                    shots.start_x,
                    105 - shots.start_x,
                ).tolist()
            )
            scored = pd.read_parquet(
                root / f"{source}/scored/{match['native_id']}.parquet"
            )
            xg += int(scored.xg.notna().sum())
            vaep += int(scored.vaep_value.notna().sum())
            xt += int(scored.xt.notna().sum())
            if source in ("wyscout", "whoscored"):
                doc = json.loads(
                    (
                        root / f"{source}/normalized/{match['native_id']}.json"
                    ).read_text()
                )
                inferred += sum(
                    e.get("inferred", False) and not e.get("derived_marker")
                    for e in doc["events"]
                )
        report["full"][source] = {
            "matches": len(matches),
            "actions": sum(sizes),
            "mean_actions": float(np.mean(sizes)) if sizes else None,
            "min_actions": min(sizes) if sizes else None,
            "max_actions": max(sizes) if sizes else None,
            "columns_match_statsbomb": all(list(c) == expected for c in columns)
            if columns
            else None,
            "invalid_coordinates": invalid,
            "attacking_shot_x_median": float(np.median(shot_x)) if shot_x else None,
            "own_xg_rows": xg,
            "vaep_rows": vaep,
            "valued_xt_rows": xt,
            "inferred_carries": inferred,
        }
    catalogue = json.loads((data_dir / "catalogue/matches.json").read_text())
    sb_sizes = [
        pq.read_metadata(
            data_dir / f"processed/spadl/{m['native_id']}.parquet"
        ).num_rows
        for m in catalogue
        if m.get("demo")
        and (data_dir / f"processed/spadl/{m['native_id']}.parquet").exists()
    ]
    report["statsbomb_reference"] = {
        "matches": len(sb_sizes),
        "actions": sum(sb_sizes),
        "mean_actions": float(np.mean(sb_sizes)),
    }
    for source in ("fotmob", "understat"):
        catalogue = root / f"catalogue_{source}.json"
        if not catalogue.exists():
            continue
        matches = json.loads(catalogue.read_text())
        counts = Counter((m["competition"], m["season"]) for m in matches)
        report["inventory"].extend(
            {
                "source": source,
                "tier": "lite",
                "competition": key[0],
                "season": key[1],
                "matches": value,
            }
            for key, value in sorted(counts.items())
        )
        shots, xg, invalid, own_goals = 0, 0, 0, 0
        for match in matches:
            doc = json.loads(
                (root / f"{source}/lite/{match['native_id']}.json").read_text()
            )
            for shot in doc["shots"]:
                shots += 1
                xg += int(shot["xg"] is not None)
                invalid += int(not (0 <= shot["x"] <= 105 and 0 <= shot["y"] <= 68))
                own_goals += int(shot["result"] == "OwnGoal" and shot["xg"] is None)
        report["lite"][source] = {
            "matches": len(matches),
            "shots": shots,
            "own_xg_rows": xg,
            "invalid_coordinates": invalid,
            "own_goals_without_xg": own_goals,
            "latest_match_date": max(m["match_date"] for m in matches)
            if matches
            else None,
        }
    save_json(root / "round2_quality_report.json", report)
    return report


if __name__ == "__main__":
    print(json.dumps(summarize(get_settings().data_dir), indent=2))
