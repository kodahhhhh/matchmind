"""Hybrid search with deterministic vectors, all mutations rolled back."""

import psycopg
from psycopg.rows import dict_row

from matchmind.analyst.commentary import apply_commentary_schema
from matchmind.api.search import query_commentary
from matchmind.config import get_settings


def test_hybrid_search_in_transaction(final_url: str) -> None:
    settings = get_settings()
    dim = settings.embed_dim
    with psycopg.connect(final_url, row_factory=dict_row) as conn:
        apply_commentary_schema(conn)
        try:
            sequences = conn.execute(
                "SELECT sequence_id,match_id FROM sequences "
                "WHERE match_id='sb:3869685' ORDER BY sequence_id LIMIT 3"
            ).fetchall()
            for i, row in enumerate(sequences):
                vector = [0.0] * dim
                vector[i] = 1.0
                text = [
                    "Dangerous counter attack down the left after a turnover",
                    "Safe backwards passing on the right",
                    "A dangerous chance from a corner",
                ][i]
                conn.execute(
                    "INSERT INTO commentary "
                    "(sequence_id,match_id,minute,text,embedding) "
                    "VALUES (%s,%s,%s,%s,%s::vector)",
                    (row["sequence_id"], row["match_id"], 80 + i, text, str(vector)),
                )
            vector = [0.0] * dim
            vector[0] = 1.0
            results = query_commentary(conn, "dangerous left", "sb:3869685", vector)
            assert results[0]["sequence_id"] == sequences[0]["sequence_id"]
            assert results[0]["team"] in ("home", "away")
            assert set(results[0]) == {
                "sequence_id",
                "match_id",
                "minute",
                "label",
                "team",
                "text",
                "score",
                "match",
            }
            assert query_commentary(conn, "dangerous", "sb:missing", vector) == []
            lexical = query_commentary(conn, "left", None, None)
            assert len(lexical) == 1
        finally:
            conn.rollback()
        assert conn.execute("SELECT count(*) AS n FROM commentary").fetchone()["n"] == 0
