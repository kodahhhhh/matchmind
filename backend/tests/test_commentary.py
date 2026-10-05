"""Fact provenance, short moments, timeline filtering and analyst evidence."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from matchpulse.analyst.commentary import (
    build_facts,
    line_errors,
    load_facts,
    parse_lines,
    prompt_facts,
    zone,
)
from matchpulse.analyst.grounding import grounding_errors
from matchpulse.analyst.tools import TOOLS, dispatch
from matchpulse.api.main import app
from matchpulse.api.repository import bundle, connect

FINAL = "sb:3869685"


def test_facts_use_our_xg_and_preserve_sequence_contract() -> None:
    with connect() as conn:
        facts = load_facts(conn, FINAL)
        shots = {
            r["event_id"]: r["xg"]
            for r in conn.execute(
                "SELECT event_id,xg FROM events WHERE match_id=%s AND type='Shot'",
                (FINAL,),
            ).fetchall()
        }
    sequences = {s["id"]: s for s in bundle(FINAL)["sequences"]}
    assert facts
    for f in facts:
        if f["sequence_id"] in sequences:
            s = sequences[f["sequence_id"]]
            assert (f["start"], f["danger"], f["sequence_outcome"]) == (
                s["start"],
                s["danger"],
                s["outcome"],
            )
        for action in f["actions"]:
            assert "sb_xg" not in action
    # Final's isolated penalty sequence must survive the <3-actions filter.
    penalty = next(
        f
        for f in facts
        if f["start"]["period"] == 2
        and any(a["action"] == "shot_penalty" for a in f["actions"])
    )
    assert any(a["action"] == "shot_penalty" for a in penalty["actions"])
    assert all(
        a["xg"] == round(shots["sb:3869685:2928"], 4)
        for a in penalty["actions"]
        if a["action"] == "shot_penalty"
    )


def test_missing_model_xg_never_falls_back_to_source(final_url: str) -> None:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(final_url, row_factory=dict_row) as conn:
        meta = conn.execute(
            "SELECT meta FROM matches WHERE match_id=%s", (FINAL,)
        ).fetchone()["meta"]
        rows = conn.execute(
            "SELECT * FROM events WHERE match_id=%s "
            "ORDER BY period,(extra->>'index')::int",
            (FINAL,),
        ).fetchall()
        seqs = conn.execute(
            "SELECT * FROM sequences WHERE match_id=%s", (FINAL,)
        ).fetchall()
        facts = build_facts(rows, meta, seqs)
    for f in facts:
        assert all(a.get("xg") is None for a in f["actions"])


def test_zone_and_format_validation() -> None:
    assert zone(30, 60) == "own half"
    assert zone(60, 60) == "left wing"
    assert zone(60, 10) == "right wing"
    assert zone(90, 34) == "inside the box"
    assert zone(None, None) is None
    f = {
        "sequence_id": FINAL + ":s1",
        "match_id": FINAL,
        "score_after": {"home": 2, "away": 1},
    }
    assert not line_errors("Messi scores for 2–1.", f)
    assert line_errors("Messi scores for 9–0.", f)
    assert line_errors("Messi scores. France restart.", f)
    assert line_errors(" ".join(["word"] * 29), f)
    f["actions"] = [{"recipient": "Messi", "to": "central midfield"}]
    assert line_errors("De Paul finds Messi on the right wing.", f)
    assert not line_errors("De Paul finds Messi in central midfield.", f)
    f["actions"] = [{"player": "St. Clair"}]
    assert not line_errors("St. Clair sends a long ball.", f)
    f["score_after"] = {"home": 1, "away": 3}
    f["start"] = {"second": 0}
    assert "Unsupported score" in line_errors("Werder lead 1–0.", f)
    f["team"] = "home"
    f["actions"] = [
        {"player": "Aké", "team": "home", "action": "clearance"},
        {"player": "Güler", "team": "away", "action": "shot"},
    ]
    assert "Own half attributed to an opponent player" in line_errors(
        "Güler shoots from his own half after Aké clears.", f
    )
    f["actions"] = [{"player": "Shaw", "recipient": "Stones", "outcome": "Unknown"}]
    assert "Unknown pass cannot be described as completed" in line_errors(
        "Shaw's corner finds Stones.", f
    )
    assert not line_errors("Shaw attempts a corner toward Stones.", f)


def test_responses_message_concatenation_keeps_complete_keyed_output() -> None:
    sid = FINAL + ":s2"
    assert parse_lines('{"' + sid + '":"France restart."} extra message', [sid]) == {
        sid: "France restart."
    }
    with pytest.raises(ValueError, match="complete commentary"):
        parse_lines('{"unexpected":"France restart."}', [sid])


def test_prompt_focus_keeps_a_goal_and_its_build_up() -> None:
    actions = [{"action": "pass"} for _ in range(20)]
    actions += [{"action": "shot", "outcome": "Goal"}, {"action": "keeper_action"}]
    assert prompt_facts({"actions": actions})["actions"] == actions[-4:]


def test_query_embedding_dimension_mismatch_degrades_before_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from matchpulse.analyst import client

    monkeypatch.setattr(
        client,
        "get_settings",
        lambda: SimpleNamespace(embed_deployment="test", embed_dim=3),
    )
    monkeypatch.setattr(
        client,
        "sync_client",
        lambda: SimpleNamespace(
            embeddings=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    data=[SimpleNamespace(embedding=[1.0, 0.0])]
                )
            )
        ),
    )
    with pytest.raises(RuntimeError, match="wrong dimension"):
        client.embed_query("dimension mismatch probe W8")


def test_commentary_windows_and_sequence_consistency() -> None:
    with TestClient(app) as client:
        response = client.get(f"/api/matches/{FINAL}/commentary")
        assert response.status_code == 200
        lines = response.json()["lines"]
        assert lines, "Generate the final's Luna commentary before contract checks"
        assert [r["start"]["t"] for r in lines] == sorted(
            r["start"]["t"] for r in lines
        )
        b = bundle(FINAL)
        seqs = {s["id"]: s for s in b["sequences"]}
        for line in lines:
            if line["sequence_id"] in seqs:
                s = seqs[line["sequence_id"]]
                assert all(
                    line[k] == s[k] for k in ("start", "team", "danger", "outcome")
                )
        index = next(
            r["index"] for r in b["minutes"] if r["period"] == 2 and r["minute"] == 79
        )
        window = client.get(
            f"/api/matches/{FINAL}/commentary?from={index}&to={index}"
        ).json()["lines"]
        assert window
        assert all(
            r["start"]["period"] == 2 and r["start"]["minute"] == 79 for r in window
        )
        assert (
            client.get(f"/api/matches/{FINAL}/commentary?from=10&to=2").status_code
            == 422
        )
        assert client.get("/api/matches/sb:invalid/commentary").status_code == 404


def test_analyst_commentary_citations() -> None:
    assert "get_commentary" in {t["name"] for t in TOOLS}
    result = asyncio.run(
        dispatch(FINAL, "get_commentary", {"from_index": 83, "to_index": 86})
    )
    assert result["lines"]
    line = result["lines"][0]
    claim = line["text"] + " [[seq:" + line["sequence_id"] + "]]"
    assert not any(grounding_errors(claim, [result]).values())
    assert "seq:" + line["sequence_id"] in result["evidence_labels"]


def test_generate_resumes_without_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from matchpulse.analyst import commentary

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("A complete match must not call Luna")

    monkeypatch.setattr(commentary, "generate_batch", forbidden)
    result = asyncio.run(commentary.generate(FINAL, concurrency=2))
    assert result["generated"] == 0
    assert result["failed_batches"] == 0
    assert result["eligible"] == result["existing"]


def test_full_text_search_does_not_request_unavailable_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from matchpulse.api import search

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("No loaded vectors: do not call Azure")

    monkeypatch.setattr(search, "embed_query", forbidden)
    results = search.search_moments("Mbappé penalty", FINAL)["results"]
    assert results
    assert "Mbappé" in results[0]["text"]
    assert len(search.search_moments("pass", FINAL, 2)["results"]) == 2
