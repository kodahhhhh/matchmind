"""Sequential, immutable FotMob snapshots and finished-match refreshes."""

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlencode

from matchpulse.config import get_settings
from matchpulse.db.load_sources import load_lite, staging_url
from matchpulse.sources.common import save_json
from matchpulse.sources.fetch import PublicFetcher
from matchpulse.sources.import_full import staged_ids
from matchpulse.sources.lite import fotmob, score_shots

LEAGUES = {
    47: ("Premier League", "England"),
    87: ("La Liga", "Spain"),
    55: ("Serie A", "Italy"),
    54: ("1. Bundesliga", "Germany"),
    53: ("Ligue 1", "France"),
    42: ("Champions League", "Europe"),
}


def refresh(
    data_dir: Path,
    fetcher: object,
    inference: object,
    *,
    seasons: list[int],
    leagues: list[int],
    snapshot: date,
    database_url: str | None = None,
    limit: int | None = None,
) -> dict:
    """Fetch only new finished details; mutable discovery is cached once/day."""
    if database_url:
        staging_url(database_url)
    target = data_dir / "sources/catalogue_fotmob.json"
    existing = (
        {m["match_id"]: m for m in json.loads(target.read_text())}
        if target.exists()
        else {}
    )
    new, skipped = 0, 0
    loaded = staged_ids(database_url, "fm")
    for season in sorted(seasons, reverse=True):
        for league in leagues:
            query = {"id": league, "season": f"{season}/{season + 1}"}
            # A historical fixture list is immutable once its season has finished.
            if season >= snapshot.year - (snapshot.month < 7):
                query["mp_snapshot"] = snapshot.isoformat()
            discovery = fetcher.fetch(
                "fotmob", "https://www.fotmob.com/api/data/leagues?" + urlencode(query)
            )
            document = json.loads(discovery.read_text())
            fixtures = document.get("fixtures", {}).get("allMatches", [])
            if not isinstance(fixtures, list):
                raise ValueError("FotMob fixture representation changed")
            for fixture in sorted(
                fixtures,
                key=lambda f: f.get("status", {}).get("utcTime", ""),
                reverse=True,
            ):
                if not fixture.get("status", {}).get("finished"):
                    continue
                native = str(fixture["id"])
                mid = f"fm:{native}"
                output = data_dir / f"sources/fotmob/lite/{native}.json"
                if mid in existing and output.exists():
                    if database_url and mid not in loaded:
                        load_lite(database_url, output)
                    skipped += 1
                    continue
                raw = fetcher.fetch(
                    "fotmob",
                    f"https://www.fotmob.com/api/data/matchDetails?matchId={native}",
                )
                match, bundle = fotmob(json.loads(raw.read_text()))
                if str(match["native_id"]) != native:
                    raise ValueError("Detail belongs to a different fixture")
                match.update(
                    competition=LEAGUES[league][0],
                    country=LEAGUES[league][1],
                    season=f"{season}/{season + 1}",
                )
                bundle = score_shots(match, bundle, inference)
                bundle.update(raw_path=str(raw), discovery_path=str(discovery))
                save_json(output, {"meta": match, **bundle})
                if database_url:
                    load_lite(database_url, output)
                existing[mid] = match
                save_json(
                    target, sorted(existing.values(), key=lambda m: m["match_id"])
                )
                new += 1
                if new % 20 == 0:
                    print(
                        json.dumps(
                            {
                                "source": "fotmob",
                                "new": new,
                                "total": len(existing),
                                "league": league,
                                "season": season,
                            }
                        ),
                        flush=True,
                    )
                if limit and new >= limit:
                    return {"new": new, "skipped": skipped, "total": len(existing)}
    return {"new": new, "skipped": skipped, "total": len(existing)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["refresh"])
    today = datetime.now(UTC).date()
    season = today.year - (today.month < 7)
    parser.add_argument("--seasons", nargs="+", type=int, default=[season, season - 1])
    parser.add_argument(
        "--leagues", nargs="+", type=int, choices=list(LEAGUES), default=list(LEAGUES)
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    settings = get_settings()
    url = staging_url(settings.database_url) if args.load else None
    from matchpulse.sources.inference import Inference

    report = refresh(
        settings.data_dir,
        PublicFetcher(settings.data_dir),
        Inference(settings.data_dir / "models"),
        seasons=args.seasons,
        leagues=args.leagues,
        snapshot=today,
        database_url=url,
        limit=args.limit,
    )
    from matchpulse.sources.reconcile import reconcile

    reconcile(settings.data_dir, url)
    save_json(settings.data_dir / "sources/fotmob_refresh_report.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
