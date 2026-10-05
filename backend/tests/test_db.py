"""Real Timescale/pgvector contract and loading tests using local StatsBomb data."""

import json
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from matchpulse.config import get_settings
from matchpulse.db import load

FINAL = "sb:3869685"


def test_schema_twice_preserves_data(final_url: str) -> None:
    load.apply_schema(final_url, get_settings().embed_dim)
    load.apply_schema(final_url, get_settings().embed_dim)
    with psycopg.connect(final_url) as conn:
        assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 4407
        assert conn.execute(
            "SELECT hypertable_name FROM timescaledb_information.hypertables "
            "WHERE hypertable_name='events'"
        ).fetchone() == ("events",)
        assert conn.execute(
            "SELECT view_name FROM timescaledb_information.continuous_aggregates "
            "WHERE view_name='minute_metrics'"
        ).fetchone() == ("minute_metrics",)
        assert (
            conn.execute(
                "SELECT count(*) FROM pg_indexes WHERE indexdef LIKE '%USING hnsw%'"
            ).fetchone()[0]
            == 2
        )
        assert (
            conn.execute("SELECT '[1,0]'::vector <=> '[1,0]'::vector").fetchone()[0]
            == 0
        )


def test_catalogue_upsert(database_url: str, data_dir: Path) -> None:
    counts = load.load_catalogue(database_url, data_dir)
    assert counts["matches"] == 4235
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM matches").fetchone()[0] == 4235
        assert (
            conn.execute("SELECT count(*) FROM teams").fetchone()[0] == counts["teams"]
        )
        assert (
            conn.execute("SELECT count(*) FROM players").fetchone()[0]
            == counts["players"]
        )
        assert conn.execute(
            "SELECT count(*) FROM matches WHERE (meta->>'demo')::boolean"
        ).fetchone()[0] == sum(m["demo"] for m in load.read_catalogue(data_dir))
        assert (
            conn.execute(
                "SELECT count(*) FROM matches "
                "WHERE (meta->>'synthetic_kickoff')::boolean"
            ).fetchone()[0]
            == 274
        )


def test_final_count_goals_coordinates_and_null_models(final_url: str) -> None:
    with psycopg.connect(final_url) as conn:
        assert conn.execute(
            "SELECT count(*), count(DISTINCT event_id) FROM events WHERE match_id=%s",
            (FINAL,),
        ).fetchone() == (4407, 4407)
        assert conn.execute(
            "SELECT count(*) FILTER (WHERE period < 5), "
            "count(*) FILTER (WHERE period = 5) FROM events "
            "WHERE type='Shot' AND result='Goal'"
        ).fetchone() == (6, 6)
        assert (
            conn.execute(
                "SELECT count(*) FROM events WHERE "
                "x NOT BETWEEN 0 AND 105 OR end_x NOT BETWEEN 0 AND 105 OR "
                "y NOT BETWEEN 0 AND 68 OR end_y NOT BETWEEN 0 AND 68"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM events WHERE xg IS NOT NULL OR vaep IS NOT NULL "
                "OR vaep_off IS NOT NULL OR vaep_def IS NOT NULL OR xt IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
        assert conn.execute("SELECT count(sb_xg) FROM events").fetchone()[0] > 0
        shot = conn.execute(
            "SELECT x,y,end_x,end_y FROM events WHERE event_id=%s", (f"{FINAL}:192",)
        ).fetchone()
        assert shot == pytest.approx((80.85, 42.5, 102.6375, 35.445))
        assert (
            conn.execute(
                "SELECT count(*) FROM events e JOIN matches m USING (match_id) "
                "WHERE abs(extract(epoch FROM (e.ts-m.kickoff_ts)) "
                "- (e.minute*60+e.second)) >= 1"
            ).fetchone()[0]
            == 0
        )


def test_final_timeline(final_url: str) -> None:
    with psycopg.connect(final_url) as conn:
        coverage = conn.execute(
            "SELECT team,count(*),max(minute),sum(shots),sum(event_count) "
            "FROM minute_metrics_view WHERE match_id=%s GROUP BY team ORDER BY team",
            (FINAL,),
        ).fetchall()
        assert [r[0] for r in coverage] == ["away", "home"]
        assert all(120 <= r[1] <= 150 and r[2] >= 120 for r in coverage)
        assert (
            sum(r[3] for r in coverage)
            == conn.execute(
                "SELECT count(*) FROM events WHERE type='Shot' AND period<5"
            ).fetchone()[0]
        )
        assert (
            sum(r[4] for r in coverage)
            == conn.execute("SELECT count(*) FROM events WHERE period<5").fetchone()[0]
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM minute_metrics_view "
                "WHERE possession NOT BETWEEN 0 AND 1 "
                "OR field_tilt NOT BETWEEN 0 AND 1 "
                "OR period=5 OR xg IS NOT NULL OR vaep IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(DISTINCT period) FROM minute_metrics_view WHERE minute=47"
            ).fetchone()[0]
            == 2
        )
        totals = conn.execute(
            "SELECT sum(possession),sum(field_tilt) FROM minute_metrics_view "
            "GROUP BY bucket,period"
        ).fetchall()
        assert all(a is None or a == pytest.approx(1) for row in totals for a in row)


def test_match_reload_and_refresh(final_url: str, data_dir: Path) -> None:
    counts = load.load_events(final_url, data_dir, match_id=FINAL, workers=1)
    assert counts == {"matches": 1, "events": 4407}
    load.refresh(final_url)
    with psycopg.connect(final_url) as conn:
        assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 4407
        assert conn.execute("SELECT sum(n_events) FROM sequences").fetchone()[0] == 4407
        assert (
            conn.execute(
                "SELECT count(*) FROM events e "
                "LEFT JOIN sequences s USING(sequence_id) "
                "WHERE s.sequence_id IS NULL"
            ).fetchone()[0]
            == 0
        )


def test_copy_failure_rolls_back_match(
    final_url: str, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = load.raw_event_row

    def invalid(*args: object) -> tuple:
        row = list(original(*args))
        row[6] = "invalid-team"
        return tuple(row)

    monkeypatch.setattr(load, "raw_event_row", invalid)
    with pytest.raises(psycopg.errors.CheckViolation):
        load.load_events(final_url, data_dir, match_id=FINAL, workers=1)
    with psycopg.connect(final_url) as conn:
        assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 4407


def test_synthetic_dates_stable(data_dir: Path) -> None:
    catalogue = load.read_catalogue(data_dir)
    dates = load.catalogue_kickoffs(catalogue)
    assert dates == load.catalogue_kickoffs(list(reversed(catalogue)))
    rebuilt = sorted(
        (
            m
            for m in catalogue
            if m["competition"] == "1. Bundesliga"
            and m["season"] == "2015/2016"
            and not m["match_date"]
        ),
        key=lambda m: m["native_id"],
    )
    assert dates[rebuilt[0]["match_id"]] == datetime(2015, 7, 1, tzinfo=UTC)
    assert (dates[rebuilt[1]["match_id"]] - dates[rebuilt[0]["match_id"]]).days == 1


def test_mapping_and_spadl_stub(data_dir: Path) -> None:
    assert load.coordinates([0, 0]) == (0, 68)
    assert load.coordinates([120, 80]) == (105, 0)
    assert load.coordinates([-2, 90]) == (0, 0)
    assert load.coordinates(None) == (None, None)
    with pytest.raises(NotImplementedError, match="awaits W2"):
        load.load_spadl_match("", data_dir, {})
    event = json.loads(
        (data_dir / "raw/statsbomb/data/events/3869685.json").read_text()
    )[191]
    match = next(m for m in load.read_catalogue(data_dir) if m["match_id"] == FINAL)
    row = dict(
        zip(
            load.EVENT_COLUMNS,
            load.raw_event_row(event, match, datetime(2022, 12, 18, tzinfo=UTC)),
            strict=True,
        )
    )
    assert row["event_id"] == "sb:3869685:192"
    assert row["sequence_id"] == "sb:3869685:s14"
    assert row["team"] == "home"
    assert row["result_name"] == "fail"
    assert row["sb_xg"] == event["shot"]["statsbomb_xg"]


def test_commentary_search_and_dimension_guard(final_url: str) -> None:
    with psycopg.connect(final_url) as conn:
        conn.execute(
            "INSERT INTO commentary(sequence_id,match_id,minute,text) "
            "VALUES (%s,%s,4,'Argentina attacks through midfield')",
            (f"{FINAL}:s14", FINAL),
        )
        assert (
            conn.execute(
                "SELECT sequence_id FROM commentary "
                "WHERE search_vector @@ plainto_tsquery('english','attacks')"
            ).fetchone()[0]
            == f"{FINAL}:s14"
        )
        conn.rollback()
    with pytest.raises(psycopg.errors.RaiseException, match="dimension differs"):
        load.apply_schema(final_url, 16)
