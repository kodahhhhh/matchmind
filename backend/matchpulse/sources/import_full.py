"""Incremental owner-provided WhoScored / Wyscout imports; models stay read only."""

import argparse
import json
from pathlib import Path

from matchpulse.config import get_settings
from matchpulse.db.load_sources import load_full, staging_url
from matchpulse.players.matching import club
from matchpulse.sources.common import dedupe, normal_name, save_json


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
        normal_name(m[s]["name"]): normal_name(club(m[s]["name"]))
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
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    s = get_settings()
    url = staging_url(s.database_url) if args.load else None
    from matchpulse.sources.inference import Inference

    inference = Inference(s.data_dir / "models")
    if args.source == "wyscout":
        from matchpulse.sources.wyscout import import_dataset

        report = import_dataset(s.data_dir, inference, url, args.limit)
    else:
        from matchpulse.sources.whoscored import import_incoming

        report = import_incoming(s.data_dir, inference, url, args.limit)
    save_json(s.data_dir / f"sources/{args.source}_import_report.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
