"""Cached and synthetic provider evidence, tier isolation and resumable imports."""

import importlib.util
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from matchpulse.api import repository, schemas
from matchpulse.api.lite import compute_lite
from matchpulse.api.main import app
from matchpulse.config import get_settings
from matchpulse.sources.common import numeric_id, save_json
from matchpulse.sources.fotmob import refresh
from matchpulse.sources.full import normalize_actions
from matchpulse.sources.lite import fotmob
from matchpulse.sources.reconcile import canonical_matches, reconcile
from matchpulse.sources.whoscored import convert_capture


def cached_fotmob() -> dict:
    for path in (get_settings().data_dir / "raw/fotmob").glob("*.json"):
        meta = json.loads(path.read_text())
        if "matchDetails?matchId=5795459" in meta.get("url", ""):
            return json.loads(path.with_suffix(".body").read_text())
    pytest.skip("Cached FotMob detail unavailable")


def test_lite_keeps_unavailable_metrics_and_rotates_away() -> None:
    meta, payload = fotmob(cached_fotmob())
    response = compute_lite({"meta": meta, **payload})
    schemas.MatchDetail.model_validate(response["match"])
    schemas.Events.model_validate(
        {"match_id": meta["match_id"], "events": response["events"]}
    )
    schemas.Timeline.model_validate(
        {"match_id": meta["match_id"], "minutes": response["minutes"]}
    )
    assert response["match"]["duration_t"] is None
    assert response["players"] == response["sequences"] == []
    for shot, event in zip(payload["shots"], response["events"], strict=True):
        assert event["x"] == pytest.approx(
            round(105 - shot["x"] if shot["team"] == "away" else shot["x"], 2)
        )
        assert event["y"] == pytest.approx(
            round(68 - shot["y"] if shot["team"] == "away" else shot["y"], 2)
        )
        assert (
            event["t"]
            is event["second"]
            is event["vaep"]
            is event["sequence_id"]
            is None
        )
        assert event["sb_xg"] is None
    assert all(
        row["momentum"] is None and row["home"]["passes"] is None
        for row in response["minutes"]
    )


def test_lite_route_gates_without_full_analytics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meta, payload = fotmob(cached_fotmob())
    response = compute_lite({"meta": meta, **payload})
    monkeypatch.setattr(repository, "catalogue", lambda: {meta["match_id"]: meta})
    monkeypatch.setattr(repository, "bundle", lambda _: response)
    client = TestClient(app)
    base = f"/api/matches/{meta['match_id']}"
    assert client.get(base).json()["data_tier"] == "lite"
    assert client.get(base + "/events").status_code == 200
    assert client.get(base + "/events?from=5").status_code == 422
    assert (
        client.post(
            base + "/counterfactual",
            json={"event_id": "irrelevant", "change": "remove_goal"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            base + "/ask", json={"question": "Compare passes", "history": []}
        ).status_code
        == 422
    )
    assert client.get(base + "/sequences").json()["sequences"] == []
    assert client.get(base + "/commentary").json()["lines"] == []


def test_fotmob_refresh_is_finished_only_and_idempotent(tmp_path: Path) -> None:
    detail = cached_fotmob()

    class Fetch:
        calls: list[str] = []

        def fetch(self, source: str, url: str) -> Path:
            self.calls.append(url)
            path = tmp_path / f"raw/{len(self.calls)}.json"
            if "leagues?" in url:
                save_json(
                    path,
                    {
                        "fixtures": {
                            "allMatches": [
                                {"id": "5795459", "status": {"finished": True}},
                                {"id": "unfinished", "status": {"finished": False}},
                            ]
                        }
                    },
                )
            else:
                save_json(path, detail)
            return path

    class Model:
        def shots(self, match: dict, events: list[dict]) -> dict:
            return {e["id"]: 0.125 for e in events}

    fetch = Fetch()
    kwargs = dict(seasons=[2026], leagues=[47], snapshot=date(2026, 10, 5))
    first = refresh(tmp_path, fetch, Model(), **kwargs)
    second = refresh(tmp_path, fetch, Model(), **kwargs)
    assert first["new"] == 1 and second["new"] == 0 and second["skipped"] == 1
    assert len([u for u in fetch.calls if "matchDetails" in u]) == 1
    assert not any("unfinished" in u for u in fetch.calls)


def test_full_precedes_lite_and_statsbomb_precedes_full() -> None:
    def entry(mid: str, tier: str) -> dict:
        return {
            "match_id": mid,
            "data_tier": tier,
            "match_date": "2026-10-01",
            "home": {"name": "Manchester United"},
            "away": {"name": "Fulham"},
            "home_score": 1,
            "away_score": 0,
        }

    rows = [entry("us:1", "lite"), entry("fm:1", "lite"), entry("ws:1", "full")]
    assert list(canonical_matches(rows)) == ["ws:1"]
    assert list(canonical_matches(rows + [entry("sb:1", "full")])) == ["sb:1"]
    conflict = {**entry("fm:2", "lite"), "home_score": 2}
    assert len(canonical_matches(rows + [conflict])) == 2


def test_reconciliation_retains_distinct_provider_aggregates(tmp_path: Path) -> None:
    meta, bundle = fotmob(cached_fotmob())
    other = {**meta, "match_id": "us:1", "source": "us", "native_id": 1}
    save_json(tmp_path / "catalogue/matches.json", [])
    save_json(tmp_path / "sources/catalogue_fotmob.json", [meta])
    save_json(tmp_path / "sources/catalogue_understat.json", [other])
    save_json(tmp_path / "sources/fotmob/lite/5795459.json", {"meta": meta, **bundle})
    save_json(
        tmp_path / "sources/understat/lite/1.json",
        {
            "meta": other,
            "provider_team_stats": {"home": {"ppda": 7}, "away": {"deep": 3}},
        },
    )
    report = reconcile(tmp_path)
    assert report["merged_fotmob_understat"] == 1
    rich = json.loads((tmp_path / "sources/fotmob/lite/5795459.json").read_text())
    assert rich["provider_team_stats"]["understat"]["home"]["ppda"] == 7
    assert rich["shots"] == bundle["shots"]
    assert reconcile(tmp_path)["merged_fotmob_understat"] == 1
    assert (
        json.loads((tmp_path / "sources/fotmob/lite/5795459.json").read_text()) == rich
    )


def capture() -> dict:
    def event(eid: int, period: int, minute: int, kind: int, x: float = 90) -> dict:
        return {
            "id": eid,
            "teamId": 10,
            "playerId": 100,
            "period": {"value": period},
            "type": {"value": kind},
            "minute": minute,
            "expandedMinute": minute,
            "second": 10,
            "x": x,
            "y": 25,
            "endX": 100,
            "endY": 25,
            "outcomeType": {"value": 1},
            "qualifiers": [],
        }

    return {
        "context": {
            "match_id": 555,
            "competition_id": 2,
            "season_id": 99,
            "competition": "Premier League",
            "season": "2025/2026",
        },
        "matchCentreData": {
            "startTime": "2026-01-01T12:00:00",
            "periodMinuteLimits": {"1": 45, "2": 90},
            "home": {
                "teamId": 10,
                "name": "Home",
                "scores": {"running": 1},
                "players": [
                    {
                        "playerId": 100,
                        "name": "Alice",
                        "isFirstEleven": True,
                        "shirtNo": 9,
                    }
                ],
            },
            "away": {
                "teamId": 20,
                "name": "Away",
                "scores": {"running": 0},
                "players": [],
            },
            "events": [
                event(1, 1, 10, 1, 50),
                event(2, 1, 11, 16),
                event(3, 2, 55, 1, 50),
                event(4, 2, 90, 30),
            ],
        },
    }


def test_whoscored_network_free_opta_conversion() -> None:
    meta, frame, events = convert_capture(capture())
    assert meta["match_id"] == "ws:555"
    assert frame.game_id.unique().tolist() == [numeric_id("ws", 555)]
    assert set(frame.type_name) >= {"pass", "shot"}
    shot = frame[frame.type_name == "shot"].iloc[0]
    assert shot.start_x == pytest.approx(94.5)
    assert shot.start_y == pytest.approx(17.0)
    assert frame[frame.period_id == 2].time_seconds.min() >= 600
    assert all(e["id"].startswith("ws:555:") for e in events)
    invalid = capture()
    invalid["matchCentreData"]["events"].pop()
    with pytest.raises(ValueError, match="period-end"):
        convert_capture(invalid)
    extra_time = capture()
    extra_time["matchCentreData"]["events"].append(
        {**extra_time["matchCentreData"]["events"][0], "id": 5, "period": {"value": 3}}
    )
    with pytest.raises(ValueError, match="period-end"):
        convert_capture(extra_time)


def test_own_goal_touch_is_not_modelled_as_shot() -> None:
    from socceraction.spadl import add_names, config

    meta = {
        "match_id": "wy:1",
        "source": "wy",
        "native_id": 1,
        "source_home_id": 10,
        "home": {"id": numeric_id("wy", 10), "name": "H"},
        "away": {"id": numeric_id("wy", 20), "name": "A"},
        "home_score": 0,
        "away_score": 1,
    }
    row = {
        "game_id": 1,
        "original_event_id": 4,
        "action_id": 0,
        "period_id": 1,
        "time_seconds": 30.0,
        "team_id": 10,
        "player_id": 100,
        "start_x": 5.0,
        "start_y": 20.0,
        "end_x": 0.0,
        "end_y": 34.0,
        "type_id": config.actiontypes.index("bad_touch"),
        "result_id": config.results.index("owngoal"),
        "bodypart_id": 0,
    }
    frame, events = normalize_actions(
        meta, add_names(pd.DataFrame([row])), {4: {"id": 4}}
    )
    assert len(frame) == 1
    assert [e["type"]["name"] for e in events] == ["Own Goal Against", "Own Goal For"]
    assert events[1]["derived_marker"] and "player" not in events[1]


def test_local_fetcher_balanced_json_and_cache_pacing(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    pytest.importorskip("json5")
    path = (
        Path(__file__).resolve().parents[2] / "scripts/sources/whoscored_local_fetch.py"
    )
    spec = importlib.util.spec_from_file_location("local_whoscored", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.embedded(
        "var matchCentreData = {events:[{name:'a } b'}], nested:{a:1}};",
        "matchCentreData",
    )
    assert result["events"][0]["name"] == "a } b"
    assert module.embedded("malicious();", "matchCentreData") is None
    assert module.embedded(
        'var args = {"matchCentreData": {"events": []}};', "matchCentreData"
    ) == {"events": []}
    assert module.BrowserCache(tmp_path).budget == 10 * 1024**3


def test_local_fetcher_replays_complete_cache_and_paces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    import hashlib
    from types import SimpleNamespace

    pytest.importorskip("playwright")
    pytest.importorskip("json5")
    path = (
        Path(__file__).resolve().parents[2] / "scripts/sources/whoscored_local_fetch.py"
    )
    spec = importlib.util.spec_from_file_location("local_whoscored_cache", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cache = module.BrowserCache(tmp_path)
    request = SimpleNamespace(
        method="GET", url="https://example.org/fixture", post_data=None
    )
    key = cache.key(request)
    save_json(
        cache.responses / f"{key}.json",
        {"complete": True, "status": 200, "headers": {}},
    )
    (cache.responses / f"{key}.body").write_bytes(b"cached")

    class Route:
        async def fulfill(self, **kwargs: object) -> None:
            assert kwargs["body"] == b"cached"

        async def continue_(self) -> None:
            pytest.fail("A complete cached request must never reach the host")

    asyncio.run(cache.route(Route(), request))
    now, waits = [100.0], []
    monkeypatch.setattr(module.time, "time", lambda: now[0])

    async def advance(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(module.asyncio, "sleep", advance)

    async def paced() -> None:
        await cache.pace("example.org", 3.1)
        await cache.pace("example.org", 3.1)
        await cache.pace("example.org", 1.1)

    asyncio.run(paced())
    assert waits == pytest.approx([3.1, 1.1])
    page_key = hashlib.sha256(request.url.encode()).hexdigest()
    save_json(
        cache.pages / f"{page_key}.variables.json", {"matchCentreData": {"events": [1]}}
    )
    assert cache.variable(request.url, "<html></html>", "matchCentreData") == {
        "events": [1]
    }
    save_json(cache.pages / f"{page_key}.json", {"final_url": request.url})
    (cache.responses / f"{key}.body").write_bytes(b'{"matches":[1]}')
    assert cache.json_document(request.url, "<html>JSON viewer</html>") == {
        "matches": [1]
    }


def test_unicode_and_national_team_aliases() -> None:
    from matchpulse.sources.common import canonical_team, decode_name

    assert decode_name(r"Atl\u00e9tico Madrid") == "Atlético Madrid"
    assert decode_name("Atlético Madrid") == "Atlético Madrid"
    assert canonical_team(r"Bayern M\u00fcnchen") == canonical_team("Bayern Munich")
    assert canonical_team("Korea Republic") == canonical_team("South Korea")


def test_wyscout_extra_time_score_is_final_not_additive() -> None:
    from matchpulse.sources.wyscout import catalogue_entry

    fixture = {
        "status": "Played",
        "duration": "ExtraTime",
        "wyId": 1,
        "dateutc": "2018-07-11 18:00:00",
        "competitionId": 28,
        "seasonId": 2,
        "teamsData": {
            "10": {"side": "home", "teamId": 10, "score": 1, "scoreET": 2},
            "20": {"side": "away", "teamId": 20, "score": 1, "scoreET": 1},
        },
    }
    meta = catalogue_entry(
        fixture, "World_Cup", {10: {"name": "Croatia"}, 20: {"name": "England"}}, {}
    )
    assert (meta["home_score"], meta["away_score"]) == (2, 1)


def test_new_lite_fixtures_follow_public_models() -> None:
    root = Path(__file__).resolve().parents[2] / "fixtures/matches/fm_5795459"
    for name, model in (
        ("match", schemas.MatchDetail),
        ("events", schemas.Events),
        ("timeline", schemas.Timeline),
        ("sequences", schemas.Sequences),
        ("players", schemas.Players),
        ("turning-points", schemas.TurningPoints),
    ):
        model.model_validate_json((root / f"{name}.json").read_text())
