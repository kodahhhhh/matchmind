"""Prepare an isolated catalogue and probe the worktree API on localhost:8013."""

import argparse
import json
from pathlib import Path

import httpx
import psycopg

from matchpulse.api import schemas
from matchpulse.config import get_settings
from matchpulse.db.load_sources import staging_url
from matchpulse.sources.common import save_json


def staged_matches(database_url: str) -> list[dict]:
    """Read the staged full/lite selection; refuse the live database URL."""
    staging_url(database_url)
    with psycopg.connect(database_url) as conn:
        return [
            row[0]
            for row in conn.execute(
                "SELECT meta FROM matches WHERE source IN ('af','us','wy','ws','fm') "
                "ORDER BY match_id"
            ).fetchall()
        ]


def prepare(data_dir: Path, database_url: str) -> Path:
    """Write only sources/verification-runtime, with temporary demo visibility."""
    selected = staged_matches(database_url)
    runtime = data_dir / "sources/verification-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "sources").mkdir(exist_ok=True)
    for name in ("models", "raw", "processed"):
        path = runtime / name
        target = data_dir / name
        if not path.exists():
            path.symlink_to(target, target_is_directory=True)
        elif path.resolve() != target.resolve():
            raise ValueError(f"Unexpected verification link: {path}")
    catalogue = json.loads((data_dir / "catalogue/matches.json").read_text())
    save_json(
        runtime / "catalogue/matches.json",
        catalogue + [{**match, "demo": True} for match in selected],
    )
    return runtime


def probe(data_dir: Path, database_url: str) -> dict:
    """Validate full GET schemas and report current lite refusals explicitly."""
    selected = staged_matches(database_url)
    report = {"base_url": "http://127.0.0.1:8013", "matches": []}
    routes = (
        ("", schemas.MatchDetail),
        ("/timeline", schemas.Timeline),
        ("/events", schemas.Events),
    )
    with httpx.Client(base_url=report["base_url"], timeout=60) as client:
        listing = client.get("/api/matches")
        listing.raise_for_status()
        cards = schemas.Matches.model_validate(listing.json())
        report["listed_matches"] = len(cards.matches)
        listed = {m.match_id for m in cards.matches}
        counts = {}
        for match in selected:
            key = (match["source"], match["data_tier"])
            if match["match_id"] not in listed or counts.get(key, 0) >= 20:
                continue
            counts[key] = counts.get(key, 0) + 1
            mid, tier = match["match_id"], match["data_tier"]
            if mid not in listed:
                raise ValueError(
                    f"Staged source missing from temporary catalogue: {mid}"
                )
            entry = {"match_id": mid, "data_tier": tier, "responses": []}
            for suffix, model in routes:
                response = client.get(f"/api/matches/{mid}{suffix}")
                row = {"route": suffix or "meta", "status": response.status_code}
                if tier in ("full", "lite"):
                    response.raise_for_status()
                    model.model_validate(response.json())
                    if suffix == "/events":
                        events = response.json()["events"]
                        row["events"] = len(events)
                        assert len({e["id"] for e in events}) == len(events)
                        for event in events:
                            assert event["id"].startswith(mid + ":")
                            assert event["team"] in ("home", "away")
                            for field, bound in (
                                ("x", 105),
                                ("y", 68),
                                ("end_x", 105),
                                ("end_y", 68),
                            ):
                                assert (
                                    event[field] is None or 0 <= event[field] <= bound
                                )
                    elif suffix == "/timeline":
                        row["minutes"] = len(response.json()["minutes"])
                elif response.status_code == 503:
                    row["limitation"] = response.json()["detail"]
                else:
                    raise ValueError(
                        f"Unexpected lite dispatch: {mid} {response.status_code}"
                    )
                entry["responses"].append(row)
            report["matches"].append(entry)
    report["lite_api_status"] = "Available: shot events and null full-event series"
    save_json(data_dir / "sources/api_sample_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "probe"))
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "prepare":
        print(prepare(settings.data_dir, settings.database_url))
    else:
        result = probe(settings.data_dir, settings.database_url)
        print(
            json.dumps(
                {
                    "listed_matches": result["listed_matches"],
                    "probed": len(result["matches"]),
                    "lite_api_status": result["lite_api_status"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
