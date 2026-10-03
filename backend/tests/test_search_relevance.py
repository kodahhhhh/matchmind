"""Smoke-test the generated corpus, including all-match metadata and FTS mode."""

import pytest
from fastapi.testclient import TestClient

from matchmind.api.main import app


@pytest.mark.parametrize(
    ("query", "words"),
    [
        ("Mbappé penalty", ("mbappé", "penalty")),
        ("long ball over the top", ("long", "ball")),
        ("header from a corner", ("corner",)),
    ],
)
def test_generated_corpus_relevance(query: str, words: tuple[str, ...]) -> None:
    with TestClient(app) as client:
        response = client.get("/api/search", params={"q": query, "limit": 5})
        assert response.status_code == 200, response.text
        rows = response.json()["results"]
        assert rows, f"Generate the demo commentary before searching: {query}"
        assert all(all(w in r["text"].lower() for w in words) for r in rows)
        assert all(
            set(r["match"])
            == {"home", "away", "competition", "season", "home_color", "away_color"}
            for r in rows
        )
        if "header" in query:
            assert all(
                any(w in r["text"].lower() for w in ("head", "header")) for r in rows
            )
