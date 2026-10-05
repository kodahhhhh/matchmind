"""Incremental owner-provided WhoScored / Wyscout imports; models stay read only."""

import argparse
import json
from pathlib import Path

from matchpulse.config import get_settings
from matchpulse.db.load_sources import load_full, staging_url
from matchpulse.sources.common import canonical_team, dedupe, normal_name, save_json


def staged_ids(database_url: str | None, source: str) -> set[str]:
    """Inspect staging once so --load also imports previously offline exports."""
    if not database_url:
        return set()
    import psycopg

    staging_url(database_url)
    with psycopg.connect(database_url) as conn:
        return {
            r[0]
            for r in conn.execute(
                "SELECT match_id FROM matches WHERE source=%s", (source,)
            ).fetchall()
        }


def publish(
    data_dir: Path,
    match: dict,
    actions: object,
    events: list[dict],
    inference: object,
    database_url: str | None,
) -> None:
    """Write source-only exports and optionally replace that staged full match."""
    folder = {"wy": "wyscout", "ws": "whoscored"}[match["source"]]
    root = data_dir / f"sources/{folder}"
    native = str(match["native_id"])
    for name, frame in (
        ("spadl", actions),
        ("scored", inference.score(match, actions, events)),
    ):
        p = root / f"{name}/{native}.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(p, index=False)
    p = root / f"normalized/{native}.json"
    save_json(p, {"meta": match, "events": events})
    if database_url:
        load_full(database_url, p, root / f"scored/{native}.parquet")


def prefer_full(data_dir: Path, catalogue: list[dict]) -> tuple[list[dict], list[dict]]:
    """Prefer StatsBomb and collapse lite duplicate identities into full provenance."""
    reference = json.loads((data_dir / "catalogue/matches.json").read_text())
    aliases = {
        normal_name(m[s]["name"]): normal_name(canonical_team(m[s]["name"]))
        for m in catalogue + reference
        for s in ("home", "away")
    }
    accepted, duplicates = dedupe(catalogue, reference, aliases)
    return accepted, duplicates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=["wyscout", "whoscored"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--load", action="store_true")
    parser.add_argument(
        "--watch", type=float, help="WhoScored scan interval, >=30 seconds"
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.watch is not None and (args.watch < 30 or args.source != "whoscored"):
        parser.error("--watch requires whoscored and an interval >=30 seconds")
    s = get_settings()
    url = staging_url(s.database_url) if args.load else None
    from matchpulse.sources.inference import Inference

    inference = Inference(s.data_dir / "models")
    import time

    while True:
        if args.source == "wyscout":
            from matchpulse.sources.wyscout import import_dataset

            report = import_dataset(s.data_dir, inference, url, args.limit)
        else:
            from matchpulse.sources.whoscored import import_incoming

            report = import_incoming(s.data_dir, inference, url, args.limit)
        save_json(s.data_dir / f"sources/{args.source}_import_report.json", report)
        print(json.dumps(report, indent=2), flush=True)
        if args.watch is None:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
