"""Hybrid pgvector/full-text search with reciprocal rank fusion."""

import re
from typing import Any

from psycopg import Connection

from matchpulse.analyst.client import embed_query
from matchpulse.api.repository import connect, require_match
from matchpulse.metrics.match import clock_label
from matchpulse.teams import match_colors


def lexical_query(query: str) -> str:
    """Reduce the common long-ball paraphrase to the recorded action words.

    The source has no over_top flags, so do not fabricate that detail in lines.
    Full-text search can still retrieve the requested long-ball possessions.
    """
    return re.sub(r"\bover the top\b", "", query, flags=re.IGNORECASE).strip()


def query_commentary(
    conn: Connection,
    query: str,
    match_id: str | None = None,
    vector: list[float] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Rank bounded indexed candidates first so cosine search can use HNSW.

    Accept a vector for transaction-isolated tests. Metadata joins happen only
    after candidate ranking. A missing vector means full-text-only search.
    """
    vector_text = str(vector) if vector is not None else None
    rows = conn.execute(
        """
        WITH terms AS (
          SELECT replace(websearch_to_tsquery('english', %(q)s)::text,
            '''header''', '(''header'' | ''head'')')::tsquery AS q
        ), lexical_candidates AS MATERIALIZED (
          SELECT c.sequence_id,
                 ts_rank_cd(c.search_vector,
                   terms.q) AS relevance
          FROM commentary c CROSS JOIN terms
          WHERE (%(match)s::text IS NULL OR c.match_id=%(match)s)
            AND c.search_vector @@ terms.q
          ORDER BY relevance DESC, c.sequence_id LIMIT 100
        ), lexical AS (
          SELECT sequence_id, row_number() OVER
            (ORDER BY relevance DESC,sequence_id) AS rank
          FROM lexical_candidates
        ), semantic_candidates AS MATERIALIZED (
          SELECT c.sequence_id,c.embedding <=> %(vector)s::vector AS distance
          FROM commentary c
          WHERE %(vector)s::vector IS NOT NULL AND c.embedding IS NOT NULL
            AND (%(match)s::text IS NULL OR c.match_id=%(match)s)
          ORDER BY c.embedding <=> %(vector)s::vector LIMIT 100
        ), semantic AS (
          SELECT sequence_id,row_number() OVER
            (ORDER BY distance,sequence_id) AS rank FROM semantic_candidates
        ), fused AS (
          SELECT coalesce(l.sequence_id,v.sequence_id) AS sequence_id,
            coalesce(1.0/(60+l.rank),0)+coalesce(1.0/(60+v.rank),0) AS score
          FROM lexical l FULL JOIN semantic v USING(sequence_id)
        ), winners AS MATERIALIZED (
          SELECT * FROM fused ORDER BY score DESC,sequence_id LIMIT %(limit)s
        )
        SELECT c.sequence_id,c.match_id,c.minute,c.text,s.team,f.score,
               coalesce((c.facts->'start'->>'period')::integer,
                 (SELECT e.period FROM events e WHERE e.match_id=c.match_id
                  AND e.sequence_id=c.sequence_id ORDER BY e.period,e.minute,
                  e.second LIMIT 1),1) AS period,
               h.name AS home,a.name AS away,m.competition,m.season
        FROM winners f JOIN commentary c USING(sequence_id)
        JOIN sequences s USING(sequence_id)
        JOIN matches m ON m.match_id=c.match_id
        JOIN teams h ON h.team_id=m.home JOIN teams a ON a.team_id=m.away
        ORDER BY f.score DESC,c.sequence_id
        """,
        {
            "q": lexical_query(query),
            "match": match_id,
            "vector": vector_text,
            "limit": max(1, min(limit, 100)),
        },
    ).fetchall()
    results = []
    for row in rows:
        hc, ac = match_colors(row["home"], row["away"])
        results.append(
            {
                "sequence_id": row["sequence_id"],
                "match_id": row["match_id"],
                "minute": row["minute"],
                "label": clock_label(row["period"], row["minute"]),
                "team": row["team"],
                "text": row["text"],
                "score": round(float(row["score"]), 6),
                "match": {
                    "home": row["home"],
                    "away": row["away"],
                    "competition": row["competition"],
                    "season": row["season"],
                    "home_color": hc,
                    "away_color": ac,
                },
            }
        )
    return results


def search_moments(query: str, match_id: str | None = None, limit: int = 20) -> dict:
    """Search all matches by default; never call Azure if no vectors are loaded."""
    if match_id:
        require_match(match_id)
    query = query.strip()
    if not query:
        return {"query": query, "results": []}
    with connect() as conn:
        vectors = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM commentary WHERE embedding IS NOT NULL "
            "AND (%s::text IS NULL OR match_id=%s)) AS present",
            (match_id, match_id),
        ).fetchone()["present"]
        vector = None
        if vectors:
            try:
                vector = list(embed_query(query))
            except Exception:
                # Never log provider payloads: preserve full-text availability.
                pass
        return {
            "query": query,
            "results": query_commentary(conn, query, match_id, vector, limit),
        }
