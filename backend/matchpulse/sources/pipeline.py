"""Resumable offline imports and daily, immutable discovery snapshots."""

import argparse
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from matchpulse.config import get_settings
from matchpulse.sources.common import dedupe, save_json, spadl
from matchpulse.sources.dynasty import convert
from matchpulse.sources.fetch import PublicFetcher
from matchpulse.sources.lite import LEAGUES, enrich_understat, score_shots, understat


def refresh(
    data_dir: Path,
    fetcher: PublicFetcher,
    inference: object,
    *,
    seasons: list[int],
    leagues: list[str],
    snapshot: date,
    limit: int | None = None,
) -> dict:
    """Discover once/day; fetch only unknown finished match detail URLs.

    Fixture lists are mutable. A transparent date query names the immutable
    discovery snapshot, so rerunning that day's command never refetches it.
    The upstream does not filter by this query; finished status comes from JSON.
    Historical collection-date queries are prohibited by the CLI.
    """
    directory = data_dir / "sources"
    path = directory / "catalogue_understat.json"
    catalogue = json.loads(path.read_text()) if path.exists() else []
    existing = {m["match_id"]: m for m in catalogue}
    new, skipped = 0, 0
    for season in seasons:
        for league in leagues:
            # Bootstrap cache is valid only on its original collection date.
            url = f"https://understat.com/getLeagueData/{league}/{season}?mp_snapshot={snapshot.isoformat()}"
            discovery_path = fetcher.fetch("understat", url, ajax=True)
            league_data = json.loads(discovery_path.read_text())
            for fixture in league_data["dates"]:
                if not fixture.get("isResult"):
                    continue
                mid = f"us:{fixture['id']}"
                output = directory / f"understat/lite/{fixture['id']}.json"
                if mid in existing and output.exists():
                    skipped += 1
                    continue
                detail_path = fetcher.fetch(
                    "understat",
                    f"https://understat.com/getMatchData/{fixture['id']}",
                    ajax=True,
                )
                match, bundle = understat(
                    fixture, json.loads(detail_path.read_text()), league, season
                )
                bundle = enrich_understat(bundle, fixture, league_data)
                bundle = score_shots(match, bundle, inference)
                bundle["raw_path"] = str(detail_path)
                bundle["discovery_path"] = str(discovery_path)
                save_json(output, {"meta": match, **bundle})
                existing[mid] = match
                new += 1
                # Resume after failures without losing successful matches.
                save_json(path, sorted(existing.values(), key=lambda m: m["match_id"]))
                if new % 20 == 0:
                    print(
                        json.dumps(
                            {
                                "source": "understat",
                                "new": new,
                                "total": len(existing),
                                "league": league,
                                "season": season,
                            }
                        ),
                        flush=True,
                    )
                if limit is not None and new >= limit:
                    return {"new": new, "skipped": skipped, "total": len(existing)}
    return {"new": new, "skipped": skipped, "total": len(existing)}


def rebuild_understat(data_dir: Path, inference: object) -> dict:
    """Reparse imported bundles from immutable cached responses, with no HTTP.

    Only already imported IDs are rebuilt. This upgrades parser/model features
    without fetching matches or relying on a worker's previously loaded modules.
    """
    from urllib.parse import urlparse

    catalogue_path = data_dir / "sources/catalogue_understat.json"
    imported = {m["match_id"] for m in json.loads(catalogue_path.read_text())}
    discoveries = {}
    for record_path in (data_dir / "raw/understat").glob("*.json"):
        record = json.loads(record_path.read_text())
        path = urlparse(record.get("url", "")).path.split("/")
        if len(path) != 4 or path[1] != "getLeagueData" or record["status"] != 200:
            continue
        key = (path[2], int(path[3]))
        if key not in discoveries or record["fetched_at"] > discoveries[key][0]:
            discoveries[key] = (record["fetched_at"], record_path.with_suffix(".body"))
    rebuilt = {}
    for (league, season), (_, path) in sorted(discoveries.items()):
        discovery = json.loads(path.read_text())
        for fixture in discovery["dates"]:
            mid = f"us:{fixture['id']}"
            if mid not in imported:
                continue
            output = data_dir / f"sources/understat/lite/{fixture['id']}.json"
            original = json.loads(output.read_text())
            raw_path = Path(original["raw_path"])
            match, bundle = understat(
                fixture, json.loads(raw_path.read_text()), league, season
            )
            bundle = enrich_understat(bundle, fixture, discovery)
            bundle = score_shots(match, bundle, inference)
            bundle.update(raw_path=str(raw_path), discovery_path=str(path))
            save_json(output, {"meta": match, **bundle})
            rebuilt[mid] = match
    if set(rebuilt) != imported:
        raise ValueError("Cached discovery does not cover every imported match")
    save_json(catalogue_path, sorted(rebuilt.values(), key=lambda m: m["match_id"]))
    return {"rebuilt": len(rebuilt), "network_requests": 0}


def import_dynasty(data_dir: Path, inference: object) -> dict:
    """Convert local licensed raw data, reuse current models and export W14 files."""
    root = data_dir / "raw/dynasty/extracted/Datasets"
    if not root.is_dir():
        raise FileNotFoundError("Fetch/extract the licensed Dynasty archive first")
    catalogue, rejections, counts = [], [], []
    for path in sorted(root.glob("*/match.json")):
        native = path.parent.name
        output = data_dir / "sources/dynasty"
        try:
            meta = json.loads(path.read_text())
            rows = [
                json.loads(line)
                for line in (path.parent / "events.jsonl").read_text().splitlines()
            ]
            match, events, omitted = convert(meta, rows)
            actions = spadl(match, events)
            values = inference.score(match, actions, events)
            for folder, frame in (("spadl", actions), ("scored", values)):
                target = output / folder / f"{native}.parquet"
                target.parent.mkdir(parents=True, exist_ok=True)
                frame.to_parquet(target, index=False)
            save_json(
                output / "normalized" / f"{native}.json",
                {"meta": match, "events": events},
            )
            catalogue.append({k: v for k, v in match.items() if k != "lineups"})
            shots = actions[actions.type_name.str.startswith("shot")]
            counts.append(
                {
                    "match_id": match["match_id"],
                    "raw_events": len(rows),
                    "normalized_events": len(events),
                    "actions": len(actions),
                    "shots": len(shots),
                    "shot_x_median": float(
                        shots.start_x.where(
                            shots.team_id == match["home"]["id"], 105 - shots.start_x
                        ).median()
                    ),
                    "xg_rows": int(values.xg.notna().sum()),
                    "vaep_rows": int(values.vaep_value.notna().sum()),
                    "xt_rows": int(values.xt.notna().sum()),
                    "omitted": omitted,
                }
            )
            print(
                json.dumps(
                    {
                        "source": "dynasty",
                        "imported": len(catalogue),
                        "match_id": match["match_id"],
                        "actions": len(actions),
                    }
                ),
                flush=True,
            )
        except (ValueError, KeyError) as exc:
            rejections.append({"native_id": native, "reason": str(exc)})
    existing = json.loads((data_dir / "catalogue/matches.json").read_text())
    accepted, duplicates = dedupe(catalogue, existing)
    allowed = {str(m["native_id"]) for m in accepted}
    quarantined = []
    # A stricter parser can reject a formerly accepted match. Keep those outputs
    # for audit, but remove them from the directories consumed by W14/loaders.
    for folder, suffix in (
        ("spadl", "parquet"),
        ("scored", "parquet"),
        ("normalized", "json"),
    ):
        for path in (data_dir / f"sources/dynasty/{folder}").glob(f"*.{suffix}"):
            if path.stem not in allowed:
                target = (
                    data_dir
                    / f"sources/dynasty/quarantine/{path.stem}/{folder}.{suffix}"
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                path.replace(target)
                quarantined.append(str(target))
    save_json(data_dir / "sources/catalogue_dynasty.json", accepted)
    report = {
        "source_files": len(list(root.glob("*/match.json"))),
        "accepted": len(accepted),
        "actions": sum(c["actions"] for c in counts),
        "counts": counts,
        "rejections": rejections,
        "duplicates": duplicates,
        "quarantined_outputs": quarantined,
        "model_transfer": (
            "Unvalidated youth-domain transfer of read-only current models"
        ),
        "game_state": "Deferred: cross-source player rating identities unavailable",
        "pass_options": "Unavailable: no freeze frames",
    }
    save_json(data_dir / "sources/dynasty_report.json", report)
    return {
        k: v
        for k, v in report.items()
        if k not in ("counts", "rejections", "duplicates")
    }


def inventory(data_dir: Path) -> dict:
    """Report imported source/tier/competition/season counts from generated files."""
    counts = Counter()
    for path in (data_dir / "sources").glob("catalogue_*.json"):
        if path.stem == "catalogue_canonical":
            continue
        for m in json.loads(path.read_text()):
            counts[
                (m.get("source"), m.get("data_tier"), m["competition"], m["season"])
            ] += 1
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "counts": [
            {
                "source": key[0],
                "tier": key[1],
                "competition": key[2],
                "season": key[3],
                "matches": count,
            }
            for key, count in sorted(counts.items())
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("import-dynasty")
    sub.add_parser("inventory")
    sub.add_parser("rebuild-understat")
    job = sub.add_parser("refresh")
    today = datetime.now(UTC).date()
    season = today.year if today.month >= 7 else today.year - 1
    job.add_argument("--seasons", type=int, nargs="+", default=[season, season - 1])
    job.add_argument(
        "--leagues", choices=list(LEAGUES), nargs="+", default=list(LEAGUES)
    )
    job.add_argument("--limit", type=int)
    args = parser.parse_args()
    directory = get_settings().data_dir
    if args.command == "inventory":
        report = inventory(directory)
    else:
        from matchpulse.sources.inference import Inference

        inference = Inference(directory / "models")
        if args.command == "import-dynasty":
            report = import_dynasty(directory, inference)
        elif args.command == "rebuild-understat":
            report = rebuild_understat(directory, inference)
        else:
            if args.limit is not None and args.limit < 1:
                parser.error("--limit must be positive")
            report = refresh(
                directory,
                PublicFetcher(directory),
                inference,
                seasons=args.seasons,
                leagues=args.leagues,
                snapshot=datetime.now(UTC).date(),
                limit=args.limit,
            )
    save_json(directory / f"sources/{args.command}_report.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
