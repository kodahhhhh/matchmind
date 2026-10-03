"""Hybrid pgvector/full-text search with reciprocal rank fusion."""

from typing import Any

from psycopg import Connection

from matchmind.analyst.client import embed_query
from matchmind.api.repository import connect, require_match
from matchmind.metrics.match import clock_label


def query_commentary(
    conn: Connection,
    query: str,
    match_id: str | None = None,
    vector: list[float] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Execute both ranked searches inside the caller's transaction.

    Accept a vector so tests can insert/rollback rows without a provider call.
    FTS-only ranking remains useful when the embedding service is unavailable.
    """
    rows = conn.execute(
        """
        WITH lexical AS (
          SELECT c.sequence_id,
                 row_number() OVER (ORDER BY ts_rank_cd(c.search_vector,
                    websearch_to_tsquery('english',%s)) DESC,
                    c.sequence_id) AS rank
          FROM commentary c
          WHERE (%s::text IS NULL OR c.match_id=%s)
            AND c.search_vector @@ websearch_to_tsquery('english',%s)
          ORDER BY rank LIMIT 100
        ), semantic AS (
          SELECT c.sequence_id,
                 row_number() OVER (ORDER BY c.embedding <=> %s::vector,
                    c.sequence_id) AS rank
          FROM commentary c
          WHERE %s::vector IS NOT NULL AND c.embedding IS NOT NULL
            AND (%s::text IS NULL OR c.match_id=%s)
          ORDER BY c.embedding <=> %s::vector LIMIT 100
        ), fused AS (
          SELECT coalesce(l.sequence_id,v.sequence_id) AS sequence_id,
                 coalesce(1.0/(60+l.rank),0)+coalesce(1.0/(60+v.rank),0) AS score
          FROM lexical l FULL JOIN semantic v USING(sequence_id)
        )
        SELECT c.sequence_id,c.match_id,c.minute,c.text,s.team,f.score,
               coalesce((SELECT e.period FROM events e WHERE e.match_id=c.match_id
                    AND e.sequence_id=c.sequence_id
                    ORDER BY e.period,e.minute,e.second LIMIT 1),1) AS period
        FROM fused f JOIN commentary c USING(sequence_id)
        JOIN sequences s USING(sequence_id)
        ORDER BY f.score DESC,c.sequence_id LIMIT %s
    """,
        (
            query,
            match_id,
            match_id,
            query,
            str(vector) if vector is not None else None,
            str(vector) if vector is not None else None,
            match_id,
            match_id,
            str(vector) if vector is not None else None,
            limit,
        ),
    ).fetchall()
    return [
        {
            "sequence_id": r["sequence_id"],
            "match_id": r["match_id"],
            "minute": r["minute"],
            "label": clock_label(r["period"], r["minute"]),
            "team": r["team"],
            "text": r["text"],
            "score": round(float(r["score"]), 6),
        }
        for r in rows
    ]


def search_moments(query: str, match_id: str | None = None) -> dict:
    """Empty commentary is a valid result and never triggers an embedding request."""
    if match_id:
        require_match(match_id)
    with connect() as conn:
        exists = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM commentary WHERE (%s::text IS NULL OR "
            "match_id=%s)) AS present",
            (match_id, match_id),
        ).fetchone()["present"]
        if not exists:
            return {"query": query, "results": []}
        try:
            vector = list(embed_query(query))
        except Exception:
            # Do not log provider payloads; graceful degradation retains full-text.
            vector = None
        return {
            "query": query,
            "results": query_commentary(conn, query, match_id, vector),
        }
