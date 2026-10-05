"""Fixture shapes against the real loaded DB, never a fixture-serving API."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from matchpulse.api import schemas as s
from matchpulse.api.main import app
from matchpulse.api.repository import bundle, catalogue

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FINAL = "sb:3869685"
DIRECTORY = FIXTURES / "matches/sb_3869685"


def assert_shape(actual: Any, examples: list[Any], path: str = "$") -> None:
    """Compare recursively to observed fixture variants (nulls/optional markers).

    Fixture list lengths and values are not contract constraints. All elements are
    checked, and Pydantic separately enforces enums including variants absent here.
    """
    if isinstance(actual, dict):
        choices = [
            e for e in examples if isinstance(e, dict) and e.keys() == actual.keys()
        ]
        assert choices, f"{path}: unexpected keys {actual.keys()}"
        for key, value in actual.items():
            assert_shape(value, [e[key] for e in choices], f"{path}.{key}")
    elif isinstance(actual, list):
        choices = [e for e in examples if isinstance(e, list)]
        assert choices, f"{path}: expected list"
        elements = [item for e in choices for item in e]
        for index, item in enumerate(actual):
            assert_shape(item, elements, f"{path}[{index}]")
    elif isinstance(actual, bool):
        assert any(isinstance(e, bool) for e in examples), path
    elif isinstance(actual, (int, float)):
        assert any(
            isinstance(e, (int, float)) and not isinstance(e, bool) for e in examples
        ), path
    else:
        assert any(type(e) is type(actual) for e in examples), (
            f"{path}: unexpected type {type(actual)}"
        )


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize(
    ("endpoint", "filename"),
    [
        ("/competitions", "competitions.json"),
        ("/matches", "matches.json"),
        (f"/matches/{FINAL}", "matches/sb_3869685/match.json"),
        *[
            (f"/matches/{FINAL}/{endpoint}", f"matches/sb_3869685/{filename}.json")
            for endpoint, filename in [
                ("events", "events"),
                ("timeline", "timeline"),
                ("sequences", "sequences"),
                ("players", "players"),
                ("turning-points", "turning-points"),
                ("commentary", "commentary"),
            ]
        ],
        (
            f"/search?q=dangerous+attacks+down+the+left&match_id={FINAL}",
            "matches/sb_3869685/search.json",
        ),
    ],
)
def test_real_get_contract(client: TestClient, endpoint: str, filename: str) -> None:
    response = client.get("/api" + endpoint)
    assert response.status_code == 200, response.text
    assert_shape(response.json(), [json.loads((FIXTURES / filename).read_text())])


def test_events_and_orientation_exactly_match_fixture(client: TestClient) -> None:
    actual = client.get(f"/api/matches/{FINAL}/events").json()["events"]
    expected = json.loads((DIRECTORY / "events.json").read_text())["events"]
    # Models may already be backfilled; only model outputs may differ.
    fields = [k for k in expected[0] if k not in ("xg", "vaep")]
    assert len(actual) == 2735
    for a, b in zip(actual, expected, strict=True):
        assert {k: a[k] for k in fields} == {k: b[k] for k in fields}
    assert [e["t"] for e in actual] == sorted(e["t"] for e in actual)
    assert all(e["period"] < 5 for e in actual)
    assert client.get(f"/api/matches/{FINAL}").json()["score"]["penalties"] == {
        "home": 4,
        "away": 2,
    }


def test_timeline_labels_and_periods(client: TestClient) -> None:
    rows = client.get(f"/api/matches/{FINAL}/timeline").json()["minutes"]
    expected = json.loads((DIRECTORY / "timeline.json").read_text())["minutes"]
    assert [(r["index"], r["period"], r["minute"], r["label"]) for r in rows] == [
        (r["index"], r["period"], r["minute"], r["label"]) for r in expected
    ]
    assert all(
        abs(r["home"]["possession"] + r["away"]["possession"] - 1) <= 0.0011
        for r in rows
    )


def test_final_change_near_mbappe_double(client: TestClient) -> None:
    turns = client.get(f"/api/matches/{FINAL}/turning-points").json()["turning_points"]
    found = [
        t
        for t in turns
        if t["start"]["period"] == 2 and 78 <= t["start"]["minute"] <= 81
    ]
    assert found, turns
    assert {"sb:3869685:2928", "sb:3869685:2987"} <= set(found[0]["key_event_ids"])
    assert found[0]["team_gaining"] == "away"


def test_all_matches_have_detail_and_null_dates(client: TestClient) -> None:
    rows = client.get("/api/matches").json()["matches"]
    assert len(rows) == len(catalogue()) == 2924
    assert all(m["has_detail"] for m in rows)
    rebuilt = next(m for m in rows if m["reconstructed"])
    assert rebuilt["match_date"] is None
    detail = client.get("/api/matches/" + rebuilt["match_id"]).json()
    assert detail["match_date"] is None
    assert detail["reconstructed"] is True


def test_event_filters_and_errors(client: TestClient) -> None:
    response = client.get(f"/api/matches/{FINAL}/events?from=3155&to=3300")
    assert response.status_code == 200
    assert all(3155 <= e["t"] <= 3300 for e in response.json()["events"])
    assert client.get(f"/api/matches/{FINAL}/events?from=20&to=10").status_code == 422
    assert client.get("/api/matches/sb:invalid/events").status_code == 404
    assert client.get(f"/api/matches/{FINAL}/sequences?sort=invalid").status_code == 422


def test_counterfactual_contract_and_quantiles(client: TestClient) -> None:
    fixture = json.loads((DIRECTORY / "counterfactual.json").read_text())
    r = client.post(
        f"/api/matches/{FINAL}/counterfactual",
        json={"event_id": fixture["event_id"], "change": fixture["change"]},
    )
    assert r.status_code == 200, r.text
    actual = r.json()
    assert_shape(actual, [fixture])
    assert actual["n_analogs"] == 40
    for side in ("home", "away"):
        for metric in ("xg", "possession"):
            b = actual["modelled"][side][metric]
            assert b["p10"] <= b["p50"] <= b["p90"]
    assert all(a["match_id"] != FINAL for a in actual["analogs"])
    assert actual["series"][0]["actual"] == {"home": 0.0, "away": 0.0}
    assert actual["series"][-1]["actual"] == {
        side: actual["actual"][side]["xg"] for side in ("home", "away")
    }
    assert (
        client.post(
            f"/api/matches/{FINAL}/counterfactual",
            json={"event_id": fixture["event_id"], "change": "no_sub"},
        ).status_code
        == 422
    )


def test_sub_counterfactual(client: TestClient) -> None:
    marker = next(m for m in bundle(FINAL)["match"]["markers"] if m["type"] == "sub")
    r = client.post(
        f"/api/matches/{FINAL}/counterfactual",
        json={"event_id": marker["event_id"], "change": "no_sub"},
    )
    assert r.status_code == 200, r.text
    s.Counterfactual.model_validate(r.json())


def test_fixture_sse_variants() -> None:
    chunks = json.loads((DIRECTORY / "ask.json").read_text())["stream"]
    adapter = TypeAdapter(s.AskChunk)
    for chunk in chunks:
        adapter.validate_python(chunk)


def test_counterfactual_reports_factual_band_and_lineup_change(
    client: TestClient,
) -> None:
    marker = next(m for m in bundle(FINAL)["match"]["markers"] if m["type"] == "sub")
    actual = client.post(
        f"/api/matches/{FINAL}/counterfactual",
        json={"event_id": marker["event_id"], "change": "no_sub"},
    ).json()
    change = actual["lineup_change"]
    assert change["restored"]["player_id"] == marker["player_off_id"]
    assert change["removed"]["player_id"] == marker["player_id"]
    for side in ("home", "away"):
        for metric in ("xg", "possession"):
            assert actual["effect"][side][metric] == pytest.approx(
                actual["modelled"][side][metric]["p50"]
                - actual["factual"][side][metric]["p50"],
                abs=1e-4,
            )


def test_shot_alternatives_contract(client: TestClient) -> None:
    fixture = json.loads((DIRECTORY / "shot-alternatives.json").read_text())
    r = client.get(f"/api/matches/{FINAL}/shots/{fixture['event_id']}/alternatives")
    assert r.status_code == 200, r.text
    actual = r.json()
    assert_shape(actual, [fixture])
    values = [o["value"] for o in actual["options"]]
    assert values == sorted(values, reverse=True)
    assert all(0 <= o["p_complete"] <= 1 for o in actual["options"])
    assert all(0 <= o["x"] <= 105 and 0 <= o["y"] <= 68 for o in actual["options"])
    # Penalties and non-shots have no passing alternative.
    for event_id in ("sb:3869685:2928", "sb:3869685:1378"):
        url = f"/api/matches/{FINAL}/shots/{event_id}/alternatives"
        assert client.get(url).status_code == 422
