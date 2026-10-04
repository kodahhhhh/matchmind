"""Read commentary with the same sequence values and clock as the match API."""

from matchmind.api.repository import bundle, connect


def get_commentary(
    match_id: str, from_index: int | None = None, to_index: int | None = None
) -> dict:
    """Return lines whose starts fall in inclusive timeline bucket indices."""
    b = bundle(match_id)
    sequences = {s["id"]: s for s in b["sequences"]}
    buckets = {(r["period"], r["minute"]): r["index"] for r in b["minutes"]}
    with connect() as conn:
        rows = conn.execute(
            "SELECT sequence_id,text,facts FROM commentary WHERE match_id=%s",
            (match_id,),
        ).fetchall()
    lines = []
    for row in rows:
        stored = row["facts"] or {}
        seq = sequences.get(row["sequence_id"])
        if seq:
            start, danger, outcome, team = (
                seq["start"],
                seq["danger"],
                seq["outcome"],
                seq["team"],
            )
        elif stored:
            start, danger, outcome, team = (
                stored["start"],
                stored["danger"],
                stored["sequence_outcome"],
                stored["team"],
            )
        else:
            continue
        index = buckets.get((start["period"], start["minute"]))
        if from_index is not None and (index is None or index < from_index):
            continue
        if to_index is not None and (index is None or index > to_index):
            continue
        lines.append(
            {
                "sequence_id": row["sequence_id"],
                "team": team,
                "start": start,
                "text": row["text"],
                "danger": danger,
                "outcome": outcome,
            }
        )
    return {
        "match_id": match_id,
        "lines": sorted(lines, key=lambda r: (r["start"]["t"], r["sequence_id"])),
    }
