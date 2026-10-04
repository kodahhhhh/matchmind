"""Identity precision, historical context and real all-corpus player API contracts."""

import json
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import psycopg
import pytest
from fastapi.testclient import TestClient

from matchmind.api.routes.players import create_player_app
from matchmind.config import get_settings
from matchmind.players import schemas, service
from matchmind.players.build import build_profiles, photos
from matchmind.players.career import aggregate, playing_minutes
from matchmind.players.matching import choose, normalise
from matchmind.players.sources import wikidata

FINAL = "sb:3869685"
MESSI = 5503
GOLDEN = Path(__file__).with_name("golden")


def candidate(pid: int, name: str, citizenship: str = "Spain", **kwargs) -> dict:
    return {
        "player_id": pid,
        "name": name,
        "country_of_citizenship": citizenship,
        **kwargs,
    }


def test_identity_requires_unique_country_consistent_candidate() -> None:
    assert normalise("Ángel Di María") == "angel di maria"
    candidates = [candidate(1, "Raúl Blanco", date_of_birth="2001-07-31")]
    # Prevent the younger namesake found during the manual audit.
    assert (
        choose(["Raúl González Blanco"], candidates, "spain", first_year=2004) is None
    )
    assert (
        choose(
            ["John Smith"],
            [candidate(1, "John Smith"), candidate(2, "John Smith")],
            "spain",
        )
        is None
    )
    assert (
        choose(["John Smith"], [candidate(1, "John Smith", "England")], "spain") is None
    )
    found = choose(
        ["Lionel Andrés Messi Cuccittini", "Lionel Messi"],
        [candidate(28003, "Lionel Messi", "Argentina", number=10)],
        "argentina",
        shirt=10,
        contextual=True,
        first_year=2004,
    )
    assert found is not None and found[0]["player_id"] == 28003


def test_historical_price_does_not_look_forward_or_use_same_day() -> None:
    values = [
        {"date": "2022-01-01", "value_eur": 20},
        {"date": "2022-12-18", "value_eur": 25},
        {"date": "2023-01-01", "value_eur": 100},
    ]
    assert service.historical_value(values, "2022-12-18", strict=True) == 20
    assert service.historical_value(values, "2022-12-31") == 25
    assert service.historical_value(values, "2021-12-31") is None
    assert service.historical_value(values, None) is None
    assert service.age_at("1987-06-24", "2022-12-18") == 35
    assert service.age_at("1987-06-24", None) is None
    assert service.season_end("2015/2016") == "2016-06-30"


def event(period: int, timestamp: str, kind: str, **extra) -> dict:
    return {"period": period, "timestamp": timestamp, "type": {"name": kind}, **extra}


def test_minutes_include_stoppage_but_exclude_breaks_shootouts_and_bench_cards() -> (
    None
):
    events = [
        event(
            1,
            "00:00:00",
            "Starting XI",
            tactics={"lineup": [{"player": {"id": 1}}, {"player": {"id": 3}}]},
        ),
        event(1, "00:47:00", "Half End"),
        event(
            2,
            "00:10:00",
            "Substitution",
            player={"id": 1},
            substitution={"replacement": {"id": 2}},
        ),
        event(2, "00:15:00", "Player Off", player={"id": 3}),
        event(2, "00:20:00", "Player On", player={"id": 3}),
        event(
            2,
            "00:30:00",
            "Bad Behaviour",
            player={"id": 2},
            bad_behaviour={"card": {"name": "Red Card"}},
        ),
        event(
            2,
            "00:40:00",
            "Bad Behaviour",
            player={"id": 4},
            bad_behaviour={"card": {"name": "Red Card"}},
        ),
        event(2, "00:48:00", "Half End"),
        event(5, "00:03:00", "Shot", player={"id": 2}),
    ]
    minutes = playing_minutes(events, [])
    assert minutes == {1: 57, 2: 20, 3: 90}
    assert 4 not in minutes


def test_per90_weights_exposure_instead_of_averaging_match_rates() -> None:
    frame = pd.DataFrame(
        {
            "minutes": [90, 10],
            "vaep": [1.0, 0.5],
            "vaep_off": [0.9, 0.4],
            "vaep_def": [0.1, 0.1],
            "xg": [0.2, 0.1],
            "goals": [0, 1],
            "shots": [2, 1],
            "progressive_passes": [8, 2],
            "progressive_carries": [2, 1],
        }
    )
    result = aggregate(frame)
    assert result["vaep_per90"] == pytest.approx(1.35)
    assert result["prog_per90"] == pytest.approx(11.7)
    assert result["vaep"] == pytest.approx(result["vaep_off"] + result["vaep_def"])


def test_commons_normalization_and_attribution_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("matchmind.players.build.raw_directory", lambda: tmp_path)
    data = {
        "query": {
            "pages": {
                "1": {
                    "title": "File:Lionel Messi.jpg",
                    "imageinfo": [
                        {
                            "thumburl": "https://upload.wikimedia.org/messi.jpg",
                            "extmetadata": {
                                "Artist": {"value": "<a>Photographer</a>"},
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                            },
                        }
                    ],
                },
                "2": {
                    "title": "File:Uncredited.jpg",
                    "imageinfo": [
                        {"url": "https://upload.wikimedia.org/uncredited.jpg"}
                    ],
                },
            }
        }
    }
    monkeypatch.setattr("matchmind.players.build.cached_json", lambda *args: data)
    result = photos(
        {
            28003: {
                "photo": "http://commons.wikimedia.org/wiki/Special:FilePath/Lionel_Messi.jpg"
            },
            1: {
                "photo": "http://commons.wikimedia.org/wiki/Special:FilePath/Uncredited.jpg"
            },
        }
    )
    assert result[28003]["photo_credit"] == "Photographer"
    assert result[28003]["photo_license"] == "CC BY-SA 4.0"
    assert 1 not in result


def test_source_throttling_stops_remaining_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def throttle(*args: object) -> dict:
        calls.append(args)
        response = httpx.Response(
            429, request=httpx.Request("GET", "https://query.wikidata.org/sparql")
        )
        raise httpx.HTTPStatusError(
            "Throttled", request=response.request, response=response
        )

    monkeypatch.setattr("matchmind.players.sources.cached_json", throttle)
    assert wikidata(list(range(250))) == {}
    assert len(calls) == 1


def test_contradictory_wikidata_dob_removes_bridge_and_photo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    directory = tmp_path / "processed/players"
    directory.mkdir(parents=True)
    (tmp_path / "catalogue").mkdir()
    (tmp_path / "catalogue/matches.json").write_text("[]")
    pd.DataFrame(
        [
            {
                "sb_player_id": 1,
                "tm_player_id": 2,
                "sb_name": "Test Name",
                "confidence": 0.99,
            }
        ]
    ).to_parquet(directory / "player_map.parquet")
    (directory / "wikidata.json").write_text(
        json.dumps(
            {"2": {"wikidata_qid": "Q123", "dob": "2001-01-01", "photo": "file"}}
        )
    )
    tm = pd.DataFrame(
        [{"player_id": 2, "name": "Test Name", "date_of_birth": "2000-01-01"}]
    )
    values = pd.DataFrame(
        [
            {
                "player_id": 2,
                "date": "2022-01-01",
                "market_value_in_eur": 10,
                "current_club_name": "Club",
            }
        ]
    )
    monkeypatch.setattr(
        "matchmind.players.build.get_settings",
        lambda: SimpleNamespace(data_dir=tmp_path),
    )
    monkeypatch.setattr(
        "matchmind.players.build.table",
        lambda name: tm if name == "players" else values,
    )
    monkeypatch.setattr(
        "matchmind.players.build.photos",
        lambda enrichment: {
            2: {
                "photo_url": "https://upload.wikimedia.org/test.jpg",
                "photo_credit": "Author",
                "photo_license": "CC0",
            }
        },
    )
    profile = build_profiles().iloc[0]
    assert profile.date_of_birth == "2000-01-01"
    assert profile.wikidata_qid is None and profile.photo_url is None
    assert json.loads((directory / "wikidata.json").read_text()) == {}


@pytest.fixture(scope="module")
def client() -> TestClient:
    service.store.cache_clear()
    service.leaderboard.cache_clear()
    service.search_index.cache_clear()
    service.search_postings.cache_clear()
    return TestClient(create_player_app())


@pytest.mark.parametrize(
    ("endpoint", "filename", "model"),
    [
        (f"/players/{MESSI}?match_id={FINAL}", "player_example.json", schemas.Profile),
        ("/players/-418560", "player_tm_only_example.json", schemas.Profile),
        ("/players?q=mbappe&limit=5", "players_search_example.json", schemas.Search),
        (
            "/players/leaderboard?metric=vaep_per90&min_minutes=900&competition=1.%20Bundesliga&season=2015%2F2016&limit=5",
            "leaderboard_example.json",
            schemas.Leaderboard,
        ),
    ],
)
def test_real_player_contract(
    client: TestClient, endpoint: str, filename: str, model: type
) -> None:
    from test_contract import assert_shape

    response = client.get("/api" + endpoint)
    assert response.status_code == 200, response.text
    model.model_validate(response.json())
    example = json.loads((GOLDEN / filename).read_text())
    model.model_validate(example)
    # Pydantic covers nullable fields absent in the single golden example.
    assert set(response.json()) == set(example)
    if endpoint.endswith("limit=5") and "/leaderboard" in endpoint:
        assert_shape(response.json(), [example])


def test_profile_has_own_model_values_and_valid_raw_ids(client: TestClient) -> None:
    profile = client.get(f"/api/players/{MESSI}?match_id={FINAL}").json()
    assert profile["transfermarkt_id"] == 28003
    assert profile["in_match"]["age"] == 35
    assert profile["career"]["matches"] > 400
    final = next(m for m in profile["matches"] if m["match_id"] == FINAL)
    assert final["goals"] == 2  # Excludes penalty shootout conversions.
    root = get_settings().data_dir
    actions = pd.read_parquet(root / "processed/vaep/3869685.parquet")
    expected = actions[
        (actions.player_id == MESSI) & (actions.period_id < 5)
    ].vaep_value.sum()
    assert final["vaep"] == pytest.approx(expected)
    assert profile["in_match"]["vaep"] == pytest.approx(expected)
    heat = profile["heatmap"]["values"]
    assert len(heat) == 96 and min(heat) >= 0 and max(heat) == 1
    for moment in profile["top_moments"]:
        native = int(moment["match_id"].split(":")[1])
        raw = json.loads(
            (root / f"raw/statsbomb/data/events/{native}.json").read_text()
        )
        event_index = int(moment["event_id"].split(":")[-1])
        e = next(e for e in raw if e["index"] == event_index)
        assert e["player"]["id"] == MESSI
        assert moment["sequence_id"] == f"sb:{native}:s{e['possession']}"


def test_search_filters_leaderboard_validation_and_unknowns(client: TestClient) -> None:
    a = client.get("/api/players?q=mbappe").json()
    b = client.get("/api/players?q=Mbappé").json()
    assert a == b and a["results"][0]["player_id"] == 3009
    assert client.get("/api/players/999999999").status_code == 404
    assert client.get(f"/api/players/{MESSI}?match_id=sb:invalid").status_code == 404
    assert client.get("/api/players/leaderboard?metric=invalid").status_code == 422
    assert client.get("/api/players?limit=0").status_code == 422
    result = client.get("/api/players/leaderboard?competition=missing").json()
    assert result["rows"] == []
    tm_only = client.get(f"/api/players/-418560?match_id={FINAL}").json()
    assert tm_only["name"] == "Erling Haaland" and not tm_only["in_dataset"]
    assert tm_only["sources"][:1] == ["transfermarkt"]
    assert tm_only["career"] is None and tm_only["heatmap"] is None
    assert tm_only["matches"] == tm_only["top_moments"] == []
    assert tm_only["in_match"] is None and tm_only["valuations"]
    haaland = client.get("/api/players?q=haaland").json()["results"]
    assert any(p["player_id"] == -418560 and not p["in_dataset"] for p in haaland)


def test_all_corpus_coverage_and_replay_availability() -> None:
    root = get_settings().data_dir / "processed/players"
    matches = pd.read_parquet(root / "matches.parquet")
    mapping = pd.read_parquet(root / "player_map.parquet")
    assert matches.match_id.nunique() == 2924
    assert matches[matches.in_db].match_id.nunique() == 493
    assert set(matches.player_id) <= set(mapping.sb_player_id)
    assert mapping.sb_player_id.is_unique
    assert mapping.tm_player_id.dropna().is_unique
    assert mapping.confidence.between(0, 1).all()
    # Undated reconstructed matches must never gain synthetic ages/prices.
    pid, mid = matches[matches.date.isna()][["player_id", "match_id"]].iloc[0]
    in_match = service.get_player_profile(int(pid), mid)["in_match"]
    assert in_match["age"] is None and in_match["market_value_eur"] is None


def test_additive_sql_is_idempotent_and_protects_photo_credits(
    database_url: str,
) -> None:
    path = Path(__file__).resolve().parents[1] / "matchmind/db/players.sql"
    with psycopg.connect(database_url) as conn:
        conn.execute(path.read_text())
        conn.execute(path.read_text())
        conn.execute(
            "INSERT INTO player_profiles (sb_player_id,name,short_name) "
            "VALUES (1,'Test','Test')"
        )
        conn.execute("INSERT INTO player_valuations VALUES (1,'2022-01-01',100,'Club')")
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        psycopg.connect(database_url) as conn,
    ):
        conn.execute(
            "UPDATE player_profiles "
            "SET photo_url='https://upload.wikimedia.org/test.jpg' WHERE sb_player_id=1"
        )
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM matches").fetchone()[0] == 4235
        assert (
            conn.execute(
                "SELECT value_eur FROM player_valuations WHERE tm_player_id=1"
            ).fetchone()[0]
            == 100
        )


def test_analyst_profile_numbers_and_citations_are_tool_grounded() -> None:
    from matchmind.analyst.grounding import grounding_errors
    from matchmind.analyst.tools import TOOLS, _dispatch

    assert any(t["name"] == "get_player_profile" for t in TOOLS)
    result = _dispatch(FINAL, "get_player_profile", {"player_id": MESSI})
    moment = result["top_moments"][0]
    text = (
        f"Messi was {result['in_match']['age']} years old. [[ev:{moment['event_id']}]]"
    )
    assert grounding_errors(text, [result]) == {
        "unsupported_numbers": [],
        "unsupported_citations": [],
    }
    assert result["display_numbers"]


def test_heatmaps_are_finite_and_normalized() -> None:
    _, _, careers, _ = service.store()
    for summary in careers.values():
        heat = np.array(summary["heatmap"]["values"])
        assert heat.shape == (96,) and np.isfinite(heat).all()
        assert ((heat >= 0) & (heat <= 1)).all()
