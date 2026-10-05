"""Opt-in real staging integration; production URLs are rejected before mutation."""

import json

import psycopg
import pytest

from matchpulse.config import get_settings
from matchpulse.db.load_sources import load_full, load_lite, staging_url


def test_staging_reloads_are_idempotent_without_fake_lite_actions() -> None:
    settings = get_settings()
    try:
        url = staging_url(settings.database_url)
    except ValueError:
        pytest.skip("Set DATABASE_URL to matchpulse_staging for the integration test")
    root = settings.data_dir / "sources"
    full = root / "dynasty/normalized/6605587a2e4dbcfcb88f2381.json"
    lite = next(iter(sorted((root / "understat/lite").glob("*.json"))), None)
    if not full.exists() or lite is None:
        pytest.skip("Cached source sample not installed")
    scored = root / f"dynasty/scored/{full.stem}.parquet"
    full_id = json.loads(full.read_text())["meta"]["match_id"]
    lite_id = json.loads(lite.read_text())["meta"]["match_id"]

    def snapshot() -> tuple:
        with psycopg.connect(url) as conn:
            return tuple(
                conn.execute(
                    "SELECT count(*),count(DISTINCT event_id),sum(vaep),"
                    "min(ts),max(ts) "
                    "FROM events WHERE match_id=%s",
                    (full_id,),
                ).fetchone()
            )

    first = load_full(url, full, scored)
    before = snapshot()
    assert load_full(url, full, scored) == first
    assert snapshot() == before
    assert before[0] == before[1] == first
    load_lite(url, lite)
    load_lite(url, lite)
    with psycopg.connect(url) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM source_lite_matches WHERE match_id=%s", (lite_id,)
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM events WHERE match_id=%s", (lite_id,)
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM sequences WHERE match_id=%s", (lite_id,)
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM events e JOIN matches m USING(match_id) "
                "WHERE match_id=%s AND extract(epoch FROM (ts-kickoff_ts)) "
                "!= (extra->>'elapsed_match_seconds')::double precision",
                (full_id,),
            ).fetchone()[0]
            == 0
        )
