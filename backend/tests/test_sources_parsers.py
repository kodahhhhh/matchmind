"""Normalization, coverage, cache replay and finished-only refresh checks."""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from matchpulse.config import get_settings
from matchpulse.db.load_sources import staging_url
from matchpulse.sources.common import coordinates, dedupe, numeric_id, spadl
from matchpulse.sources.dynasty import convert, coverage
from matchpulse.sources.lite import fotmob, understat
from matchpulse.sources.pipeline import refresh
from matchpulse.sources.wyscout import convert_events


def cached(source: str, fragment: str) -> dict:
    root = get_settings().data_dir / "raw" / source
    for p in root.glob("*.json"):
        record = json.loads(p.read_text())
        if fragment in record.get("url", "") and record.get("status") == 200:
            return json.loads(p.with_suffix(".body").read_text())
    pytest.skip(f"Cached {source} fixture unavailable: {fragment}")


def test_coordinates_clipping_and_y_inversion() -> None:
    assert coordinates(497, 0, 497, 328) == (105, 68)
    assert coordinates(0, 328, 497, 328) == (0, 0)
    assert coordinates(600, -1, 497, 328) == (105, 68)
    with pytest.raises(ValueError):
        coordinates(float("nan"), 0, 1, 1)
    assert 2**48 <= numeric_id("af", "native") < 2**53
    assert numeric_id("af", "native") != numeric_id("us", "native")


def test_dedupe_prefers_statsbomb_and_quarantines_conflicts() -> None:
    def row(mid: str, score: int = 2, day: str | None = "2018-06-15") -> dict:
        return {
            "match_id": mid,
            "match_date": day,
            "gender": "male",
            "home": {"name": "FRANCE"},
            "away": {"name": "Perú"},
            "home_score": score,
            "away_score": 0,
        }

    accepted, rejected = dedupe(
        [row("wy:1"), row("wy:2", 3), row("wy:3", day=None)], [row("sb:1")]
    )
    assert [m["match_id"] for m in accepted] == ["wy:3"]
    assert rejected == [
        {"match_id": "wy:1", "preferred": "sb:1", "reason": "duplicate"},
        {"match_id": "wy:2", "preferred": "sb:1", "reason": "score_conflict"},
    ]


@pytest.mark.parametrize(
    "url", ["postgresql://u:p@localhost/matchmind", "dbname=other", "host=localhost"]
)
def test_staging_guard_rejects_before_connection(url: str) -> None:
    with pytest.raises(ValueError, match="matchpulse_staging"):
        staging_url(url)
    assert staging_url("dbname=matchpulse_staging") == "dbname=matchpulse_staging"


def test_wyscout_offline_socceraction_converter() -> None:
    event = {
        "id": 11,
        "matchId": 123,
        "teamId": 9,
        "playerId": 8,
        "matchPeriod": "1H",
        "eventSec": 12.0,
        "eventId": 10,
        "eventName": "Shot",
        "subEventId": 100,
        "subEventName": "Shot",
        "positions": [{"x": 90, "y": 50}, {"x": 100, "y": 50}],
        "tags": [{"id": 101}, {"id": 402}, {"id": 1801}],
    }
    result = convert_events([event], home_team_id=9)
    assert result.type_name.tolist() == ["shot"]
    assert result.start_x.tolist() == [94.5]
    assert result.start_y.tolist() == [34.0]
    assert result.original_event_id.tolist() == [11]
    assert result.home_team_id.tolist() == [9]


def test_cached_fotmob_has_shots_without_full_events() -> None:
    payload = cached("fotmob", "matchDetails?matchId=5795459")
    match, bundle = fotmob(payload)
    assert match["data_tier"] == "lite" and match["match_id"] == "fm:5795459"
    assert bundle["shots"] and bundle["provider_momentum"] and bundle["team_stats"]
    assert not bundle["capabilities"]["full_events"]
    assert all(s["xg"] is None and s["second"] is None for s in bundle["shots"])


def test_cached_understat_preserves_missing_clock_and_provider_xg() -> None:
    fixtures = cached("understat", "getLeagueData/EPL/2026")
    fixture = next(m for m in fixtures["dates"] if m["id"] == "31229")
    match, bundle = understat(
        fixture, cached("understat", "getMatchData/31229"), "EPL", 2026
    )
    assert match["data_tier"] == "lite" and match["training"] is False
    shot = bundle["shots"][0]
    assert shot["x"] == pytest.approx(float(shot["source_extra"]["X"]) * 105)
    assert shot["y"] == pytest.approx(float(shot["source_extra"]["Y"]) * 68)
    assert shot["xg"] is None and shot["provider_xg"] >= 0
    assert shot["period"] is None and shot["second"] is None
    assert bundle["lineups"]["home"] and not bundle["capabilities"]["vaep"]


def test_cached_dynasty_rejects_single_team_and_matches_spadl_columns() -> None:
    root = get_settings().data_dir / "raw/dynasty/extracted/Datasets"
    path = root / "6605587a2e4dbcfcb88f2381"
    if not path.exists():
        pytest.skip("Dynasty cached raw fixture not installed")
    meta = json.loads((path / "match.json").read_text())
    raw = [
        json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()
    ]
    match, events, _ = convert(meta, raw)
    actions = spadl(match, events)
    reference = pd.read_parquet(
        get_settings().data_dir / "processed/spadl/3869685.parquet"
    )
    assert set(actions) == set(reference)
    assert actions.action_id.tolist() == list(range(len(actions)))
    assert actions[["start_x", "end_x"]].ge(0).all().all()
    assert actions[["start_x", "end_x"]].le(105).all().all()
    shots = actions[actions.type_name.str.startswith("shot")]
    acting_x = np.where(
        shots.team_id == match["home"]["id"], shots.start_x, 105 - shots.start_x
    )
    assert np.median(acting_x) > 70
    assert "missing_away_identity_or_lineup" in coverage(
        {**meta, "away_team_line_up": []}, raw
    )


def test_finished_only_refresh_is_idempotent(tmp_path: Path) -> None:
    fixture = {
        "id": "1",
        "isResult": True,
        "datetime": "2026-09-01 12:00:00",
        "h": {"id": "10", "title": "Home"},
        "a": {"id": "20", "title": "Away"},
        "goals": {"h": "0", "a": "0"},
    }
    details = {"shots": {"h": [], "a": []}, "rosters": {"h": {}, "a": {}}}

    class Fetch:
        def __init__(self) -> None:
            self.details = 0

        def fetch(self, source: str, url: str, *, ajax: bool) -> Path:
            if "getMatchData" in url:
                self.details += 1
                value = details
            else:
                value = {"dates": [fixture, {**fixture, "id": "2", "isResult": False}]}
            p = tmp_path / (
                "detail.json" if "getMatchData" in url else "discovery.json"
            )
            p.write_text(json.dumps(value))
            return p

    class Predictor:
        def shots(self, match: dict, events: list[dict]) -> dict:
            return {}

    f = Fetch()
    kwargs = {"seasons": [2026], "leagues": ["EPL"], "snapshot": date(2026, 10, 5)}
    assert refresh(tmp_path, f, Predictor(), **kwargs)["new"] == 1
    assert refresh(tmp_path, f, Predictor(), **kwargs)["new"] == 0
    assert f.details == 1
