"""Repair source unicode labels and dedupe existing exports without refetching."""

import argparse
import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from matchpulse.config import get_settings
from matchpulse.db.load_sources import staging_url
from matchpulse.sources.common import decode_name, save_json
from matchpulse.sources.import_full import prefer_full


def labels(value: object) -> object:
    """Normalize labels while retaining original source_extra dictionaries."""
    if isinstance(value, str):
        return decode_name(value)
    if isinstance(value, list):
        return [labels(v) for v in value]
    if isinstance(value, dict):
        return {
            k: v if k in ("source_extra", "source_match") else labels(v)
            for k, v in value.items()
        }
    return value


def repair(data_dir: Path, database_url: str | None) -> dict:
    """Retain duplicate files in quarantine; only update/delete our staging rows."""
    if database_url:
        staging_url(database_url)
    root = data_dir / "sources"
    catalogue = root / "catalogue_wyscout.json"
    original = json.loads(catalogue.read_text())
    accepted, duplicates = prefer_full(data_dir, labels(original))
    keep = {m["match_id"] for m in accepted}
    modified = 0
    for entry in original:
        native = str(entry["native_id"])
        if entry["match_id"] not in keep:
            for folder, suffix in (
                ("normalized", "json"),
                ("spadl", "parquet"),
                ("scored", "parquet"),
            ):
                p = root / f"wyscout/{folder}/{native}.{suffix}"
                if p.exists():
                    target = (
                        root
                        / f"wyscout/quarantine/duplicates/{native}/{folder}.{suffix}"
                    )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    p.replace(target)
            continue
        p = root / f"wyscout/normalized/{native}.json"
        document = json.loads(p.read_text())
        corrected = labels(document)
        if corrected != document:
            save_json(p, corrected)
            modified += 1
        if database_url:
            with psycopg.connect(database_url) as conn:
                conn.execute(
                    "UPDATE matches SET meta=%s WHERE match_id=%s AND source='wy'",
                    (Jsonb(corrected["meta"]), entry["match_id"]),
                )
                for team in corrected["meta"]["home"], corrected["meta"]["away"]:
                    conn.execute(
                        "UPDATE teams SET name=%s WHERE team_id=%s",
                        (team["name"], team["id"]),
                    )
    if database_url:
        with psycopg.connect(database_url) as conn:
            for duplicate in duplicates:
                mid = duplicate["match_id"]
                if not mid.startswith("wy:"):
                    raise ValueError("Only Wyscout source rows may be retired")
                for table in (
                    "commentary",
                    "gamestate_windows",
                    "sequences",
                    "events",
                    "source_lite_matches",
                    "matches",
                ):
                    conn.execute(f"DELETE FROM {table} WHERE match_id=%s", (mid,))
    save_json(catalogue, accepted)
    report = {
        "accepted": len(accepted),
        "updated_labels": modified,
        "duplicates": duplicates,
        "network_requests": 0,
        "score_values_changed": False,
    }
    save_json(root / "wyscout_label_repair_report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args()
    s = get_settings()
    print(
        json.dumps(repair(s.data_dir, s.database_url if args.load else None), indent=2)
    )
