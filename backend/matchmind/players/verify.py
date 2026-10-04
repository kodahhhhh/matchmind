"""Reproducible before/after coverage and isolated local API evidence."""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from time import perf_counter

import httpx
import pandas as pd
import psycopg

from matchmind.config import get_settings
from matchmind.players import schemas
from matchmind.players.bulk import atomic_json
from matchmind.players.career import build_coverage


def counts(profiles: pd.DataFrame, matches: pd.DataFrame) -> dict:
    """Compute player and exposure coverage directly from published artifacts."""
    dataset = profiles[profiles.sb_player_id > 0]
    minutes = matches.minutes.sum()
    result = {"searchable_profiles": len(profiles), "dataset_players": len(dataset)}
    for field in (
        "tm_player_id",
        "wikidata_qid",
        "photo_url",
        "date_of_birth",
        "height_cm",
        "nationality",
    ):
        ids = set(dataset.loc[dataset[field].notna(), "sb_player_id"])
        observed = float(matches[matches.player_id.isin(ids)].minutes.sum())
        result[field] = {
            "players": len(ids),
            "player_share": len(ids) / len(dataset),
            "minutes": observed,
            "minute_share": observed / minutes,
            "all_profiles": int(profiles[field].notna().sum()),
        }
    linked = set(
        dataset.loc[
            dataset.tm_player_id.notna() | dataset.wikidata_qid.notna(), "sb_player_id"
        ]
    )
    result["either_identity"] = {
        "players": len(linked),
        "player_share": len(linked) / len(dataset),
        "minute_share": float(
            matches[matches.player_id.isin(linked)].minutes.sum() / minutes
        ),
    }
    return result


def endpoint_evidence(origin: str) -> dict:
    """Validate real HTTP models, negative IDs, ordering and varied search latency."""
    result = {}
    endpoints = [
        ("/api/players/5503?match_id=sb:3869685", schemas.Profile),
        ("/api/players/-418560?match_id=sb:3869685", schemas.Profile),
        (
            "/api/players/leaderboard?metric=vaep_per90&min_minutes=900&competition=1.%20Bundesliga&season=2015%2F2016&limit=5",
            schemas.Leaderboard,
        ),
    ]
    with httpx.Client(base_url=origin, timeout=60) as client:
        for endpoint, model in endpoints:
            timings = []
            for _ in range(4):
                started = perf_counter()
                response = client.get(endpoint)
                timings.append(round((perf_counter() - started) * 1000, 3))
                response.raise_for_status()
                model.model_validate(response.json())
            result[endpoint] = timings
        negative = client.get("/api/players/-418560?match_id=sb:3869685").json()
        assert not negative["in_dataset"]
        assert negative["career"] is None and negative["heatmap"] is None
        assert negative["top_moments"] == negative["matches"] == []
        assert negative["in_match"] is None
        latencies = []
        for query in (
            "mbappe",
            "Mbappé",
            "haaland",
            "garcia",
            "jo",
            "a",
            "zzzznotfound",
            "",
            "joao pedro",
            "henry",
        ):
            timings = []
            for _ in range(10):
                started = perf_counter()
                response = client.get("/api/players", params={"q": query, "limit": 20})
                timings.append(round((perf_counter() - started) * 1000, 3))
                response.raise_for_status()
                parsed = schemas.Search.model_validate(response.json())
                flags = [r.in_dataset for r in parsed.results]
                assert flags == sorted(flags, reverse=True)
            latencies.extend(timings)
            result["search:" + query] = timings
        result["search_summary"] = {
            "requests": len(latencies),
            "max_ms": max(latencies),
            "p50_ms": float(pd.Series(latencies).quantile(0.5)),
            "p95_ms": float(pd.Series(latencies).quantile(0.95)),
        }
        assert result["search_summary"]["max_ms"] < 100, result["search_summary"]
    return result


def verify(origin: str | None = None) -> dict:
    """Write evidence without touching frontend, fixtures or the shared API."""
    root = get_settings().data_dir
    output = root / "processed/players"
    matches = pd.read_parquet(output / "matches.parquet")
    profiles = pd.read_parquet(output / "profiles.parquet")
    baseline = root / "raw/players/w11b-before"
    before = counts(pd.read_parquet(baseline / "profiles.parquet"), matches)
    after = counts(profiles, matches)
    mapping = pd.read_parquet(output / "player_map.parquet")
    published = profiles[profiles.in_dataset].set_index("sb_player_id")
    indexed = mapping.set_index("sb_player_id")
    for field in ("tm_player_id", "wikidata_qid"):
        pd.testing.assert_series_equal(
            indexed[field].sort_index(),
            published[field].sort_index(),
            check_names=False,
        )
    assert set(matches.player_id) == set(mapping.sb_player_id)
    assert profiles.sb_player_id.is_unique and mapping.sb_player_id.is_unique
    assert mapping.tm_player_id.dropna().is_unique
    assert profiles.loc[profiles.in_dataset, "sb_player_id"].gt(0).all()
    assert (
        profiles.loc[~profiles.in_dataset, "sb_player_id"]
        .eq(-profiles.loc[~profiles.in_dataset, "tm_player_id"])
        .all()
    )
    assert (
        profiles.loc[profiles.photo_url.notna(), ["photo_credit", "photo_license"]]
        .notna()
        .all()
        .all()
    )
    linked = mapping.tm_player_id.notna() | mapping.wikidata_qid.notna()
    assert mapping.loc[linked, "confidence"].ge(0.8).all()
    spot = json.loads((output / "spot_check_w11b.json").read_text())
    old_map = pd.read_parquet(baseline / "player_map.parquet").set_index("sb_player_id")
    current = mapping.set_index("sb_player_id")
    for row in spot["rows"]:
        assert pd.isna(old_map.loc[row["sb_player_id"], "tm_player_id"])
        assert current.loc[row["sb_player_id"], "wikidata_qid"] == row["wikidata_qid"]
        if row["tm_player_id"] is not None:
            assert (
                int(current.loc[row["sb_player_id"], "tm_player_id"])
                == row["tm_player_id"]
            )
    log = root / "raw/players/bulk/requests.jsonl"
    requests = [json.loads(r) for r in log.read_text().splitlines()]
    by_source = {}
    for source in sorted({r["source"] for r in requests}):
        rows = [r for r in requests if r["source"] == source]
        by_source[source] = {
            "requests": len(rows),
            "statuses": dict(Counter(str(r["status"]) for r in rows)),
            "api_errors": dict(Counter(r["error"] for r in rows if r["error"])),
        }
    with psycopg.connect(get_settings().database_url) as conn:
        db = conn.execute(
            "SELECT (SELECT count(*) FROM player_profiles), "
            "(SELECT count(*) FROM player_valuations), "
            "(SELECT count(*) FROM player_careers), "
            "(SELECT count(*) FROM player_profiles WHERE photo_url IS NOT NULL)"
        ).fetchone()
    result = {
        "at": datetime.now(UTC).isoformat(),
        "before": before,
        "after": after,
        "competition_seasons": build_coverage(),
        "before_competition_seasons": json.loads(
            (baseline / "coverage.json").read_text()
        ),
        "spot_check": spot,
        "requests": by_source,
        "database": dict(
            zip(("profiles", "valuations", "careers", "photos"), db, strict=True)
        ),
        "valuations": len(pd.read_parquet(output / "valuations.parquet")),
    }
    if origin:
        result["endpoints"] = endpoint_evidence(origin)
    atomic_json(output / "w11b_verification.json", result)
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k
                not in {
                    "competition_seasons",
                    "before_competition_seasons",
                    "spot_check",
                }
            },
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--origin", help="Isolated local app, e.g. http://127.0.0.1:8040"
    )
    args = parser.parse_args()
    verify(args.origin)
