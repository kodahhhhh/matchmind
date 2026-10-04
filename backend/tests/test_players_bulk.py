"""Precision, provider retry/caching and universal player profile regressions."""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from matchmind.config import get_settings
from matchmind.players import bulk, service
from matchmind.players.build import free_license, load_database
from matchmind.players.coverage_matching import club_overlap, select_bridge
from matchmind.players.matching import name_score, normalise


@pytest.mark.parametrize(
    "licence",
    [
        "CC BY 4.0",
        "CC BY-SA 2.5",
        "CC BY-SA 3.0 nl",
        "CC0",
        "Public domain",
        "GFDL 1.2",
    ],
)
def test_explicit_free_licences(licence: str) -> None:
    assert free_license(licence)


@pytest.mark.parametrize(
    "licence",
    ["CC BY-NC 4.0", "CC BY-ND 4.0", "Fair use", "Copyrighted", "", "CC BY-SA 4.0 NC"],
)
def test_nonfree_or_unknown_licences(licence: str) -> None:
    assert not free_license(licence)


def test_retry_after_and_cached_maxlag_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        bulk, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path)
    )
    sleeps = []
    monkeypatch.setattr(bulk.time, "sleep", sleeps.append)
    request = httpx.Request("GET", bulk.WD_API)
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "17"}, request=request),
            httpx.Response(
                200,
                json={"error": {"code": "maxlag"}},
                headers={"Retry-After": "5"},
                request=request,
            ),
            httpx.Response(
                200, json={"entities": {"Q1": {"id": "Q1"}}}, request=request
            ),
        ]
    )
    calls = []

    def get(url: str, **kwargs: object) -> httpx.Response:
        calls.append((url, kwargs))
        return next(responses)

    monkeypatch.setattr(bulk.httpx, "get", get)
    params = {"ids": "Q1", "maxlag": "5"}
    expected = {"entities": {"Q1": {"id": "Q1"}}}
    assert bulk.request_json(bulk.WD_API, params, "test") == expected
    assert bulk.request_json(bulk.WD_API, params, "test") == expected
    assert len(calls) == 3 and 17 in sleeps and 5 in sleeps
    logs = [
        json.loads(s)
        for s in (tmp_path / "raw/players/bulk/requests.jsonl").read_text().splitlines()
    ]
    assert [r["status"] for r in logs] == [429, 200, 200]
    assert bulk.retry_delay("7", 0) == 7
    monkeypatch.setattr(bulk.time, "time", lambda: 0)
    assert bulk.retry_delay("Thu, 01 Jan 1970 00:00:25 GMT", 0) == 25


def test_duplicate_p2446_bridge_is_never_guessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        bulk, "get_settings", lambda: SimpleNamespace(data_dir=tmp_path)
    )
    rows = [
        {"item": {"value": "http://www.wikidata.org/entity/" + q}, "tm": {"value": t}}
        for q, t in [("Q1", "10"), ("Q2", "10"), ("Q3", "20"), ("Q4", "bad")]
    ]
    monkeypatch.setattr(bulk, "sparql", lambda *args: rows)
    assert bulk.tm_index() == {20: "Q3"}


def statement(value: object, rank: str = "normal", **kwargs: object) -> dict:
    return {
        "rank": rank,
        "mainsnak": {"snaktype": "value", "datavalue": {"value": value}},
        **kwargs,
    }


def test_claims_preserve_date_precision_and_height_units() -> None:
    assert bulk.exact_date("+00000001980-03-12T00:00:00Z") == "1980-03-12"
    assert bulk.exact_date("+1980-00-00T00:00:00Z") is None
    assert bulk.exact_date("+19200-03-12T00:00:00Z") is None
    entity = {
        "id": "Q1",
        "labels": {"en": {"value": "Player"}},
        "claims": {
            "P569": [statement({"time": "+1980-00-00T00:00:00Z", "precision": 9})],
            "P2048": [
                statement(
                    {"amount": "+1.83", "unit": "http://www.wikidata.org/entity/Q11573"}
                )
            ],
            "P18": [statement("Wrong.jpg", "deprecated"), statement("Correct.jpg")],
            "P27": [statement({"id": "Q29"})],
        },
    }
    r = bulk.describe(entity)
    assert r["dob"] is None and r["height_cm"] == 183
    assert r["photo"] == "Correct.jpg" and r["countries"] == ["Q29"]
    entity["claims"]["P569"] = [
        statement({"time": "+1980-03-12T00:00:00Z", "precision": 11})
    ]
    assert bulk.describe(entity)["dob"] == "1980-03-12"
    entity["claims"]["P569"].append(
        statement({"time": "+1980-03-13T00:00:00Z", "precision": 11})
    )
    assert bulk.describe(entity)["dob"] is None


def test_alias_match_requires_unique_corroborated_identity() -> None:
    assert normalise("Łukasz Ødegaard") == "lukasz odegaard"
    assert normalise("Иван Петров") == "иван петров"
    assert name_score(["张伟"], "李明") == 0
    assert name_score([""], "") == 0
    sb = {
        "names": {"Łukasz Example"},
        "countries": {"poland"},
        "first_year": 2015,
        "appearances": {("2015-10-01", "barcelona")},
    }
    base = {
        "names": ["Lukasz Example"],
        "dob": "1990-01-01",
        "countries": ["Q36"],
        "clubs": [],
    }
    labels = {"Q36": {"names": ["Poland"]}}
    assert select_bridge(sb, [base], labels, {})[1] >= 0.8
    assert select_bridge(sb, [base, dict(base)], labels, {}) is None
    assert select_bridge(sb, [{**base, "dob": "2010-01-01"}], labels, {}) is None
    assert select_bridge(sb, [{**base, "countries": []}], labels, {}) is None
    nickname = {**base, "names": ["Fred"]}
    assert select_bridge({**sb, "names": {"Fred"}}, [nickname], labels, {}) is None


def test_club_evidence_must_overlap_verified_match_date() -> None:
    sb = {"appearances": {("1971-06-02", "ajax")}}
    labels = {"Q1": {"names": ["AFC Ajax", "Ajax"]}}
    spell = {"qid": "Q1", "start": [], "end": []}
    assert not club_overlap(sb, {"clubs": [spell]}, labels)
    spell.update(
        {
            "start": [{"time": "+1964-00-00T00:00:00Z", "precision": 9}],
            "end": [{"time": "+1973-00-00T00:00:00Z", "precision": 9}],
        }
    )
    assert club_overlap(sb, {"clubs": [spell]}, labels)
    assert not club_overlap(
        {"appearances": {("1980-06-02", "ajax")}}, {"clubs": [spell]}, labels
    )


def test_every_tm_identity_is_searchable_and_ids_do_not_collide() -> None:
    profiles, histories, careers, _ = service.store()
    frame = pd.read_parquet(
        get_settings().data_dir / "processed/players/profiles.parquet"
    )
    tm = pd.read_csv(
        get_settings().data_dir / "raw/players/transfermarkt/players.csv.gz",
        usecols=["player_id"],
    )
    assert set(frame.tm_player_id.dropna().astype(int)) == set(tm.player_id)
    assert int(frame.in_dataset.sum()) == 7563
    assert {pid for pid, p in profiles.items() if p["in_dataset"]} == {
        int(pid) for pid in careers
    }
    assert set(r["player_id"] for _, _, r in service.search_index()) == set(profiles)
    for pid, p in profiles.items():
        assert p["in_dataset"] == (pid > 0)
        assert ("statsbomb" in p["sources"]) == p["in_dataset"]
        assert ("transfermarkt" in p["sources"]) == (p["tm_player_id"] is not None)
        assert ("wikidata" in p["sources"]) == (p["wikidata_qid"] is not None)
        if pid < 0:
            assert pid == -p["tm_player_id"] and "statsbomb" not in p["sources"]
    assert len(histories) > 40000


def test_index_matches_scan_and_ranks_dataset_then_market_value() -> None:
    profiles, _, _, _ = service.store()
    for query in [
        "mbappe",
        "haaland",
        "garcia",
        "jo",
        "a",
        "notfoundzzzz",
        "",
        "joao pedro",
    ]:
        tokens = service.normalise(query).split()
        index = service.search_index()

        def hit(names: list[str], tokens: list[str] = tokens) -> bool:
            return any(all(t in name for t in tokens) for name in names)

        # real-name matches rank before alias-only matches, each in index order
        primary = [row for _, prim, row in index if not tokens or hit(prim)]
        alias = [
            row for names, prim, row in index if tokens and not hit(prim) and hit(names)
        ]
        expected = (primary + alias)[:20]
        assert service.search_players(query)["results"] == expected
        # within each group, dataset players first, then market value
        for group in (primary[:20], alias[:20]):
            keys = [
                (
                    not r["in_dataset"],
                    -(profiles[r["player_id"]]["market_value_eur"] or 0),
                )
                for r in group
            ]
            assert keys == sorted(keys)


def test_tm_only_tool_does_not_claim_observed_career() -> None:
    result = service.analyst_profile(-418560, "sb:3869685")
    assert result["career"] is None and result["in_match"] is None
    assert result["metric_notes"]["scope"] == (
        "Biography and valuations; no observations in the training corpus"
    )
    assert result["display_numbers"] and result["evidence_labels"] == {}


def test_reloading_catalogue_is_idempotent(database_url: str) -> None:
    import psycopg

    with psycopg.connect(database_url) as conn:
        conn.execute(
            (
                Path(__file__).resolve().parents[1] / "matchmind/db/players.sql"
            ).read_text()
        )
        conn.execute(
            "INSERT INTO player_profiles "
            "(sb_player_id, name, short_name, tm_player_id, in_dataset) "
            "VALUES (-999999999, 'Stale', 'Stale', 999999999, false)"
        )
    first = load_database(database_url)
    with psycopg.connect(database_url) as conn:
        first_counts = conn.execute(
            "SELECT (SELECT count(*) FROM player_profiles), "
            "(SELECT count(*) FROM player_valuations)"
        ).fetchone()
    second = load_database(database_url)
    assert first == second
    with psycopg.connect(database_url) as conn:
        assert (
            conn.execute(
                "SELECT (SELECT count(*) FROM player_profiles), "
                "(SELECT count(*) FROM player_valuations)"
            ).fetchone()
            == first_counts
        )
        assert first_counts[0] >= first["profiles"]
        assert first_counts[1] >= first["valuations"]
        assert (
            conn.execute(
                "SELECT count(*) FROM player_profiles WHERE sb_player_id=-999999999"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM player_profiles WHERE NOT in_dataset "
                "AND sb_player_id <> -tm_player_id"
            ).fetchone()[0]
            == 0
        )
