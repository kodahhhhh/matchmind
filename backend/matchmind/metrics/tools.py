"""Pure analyst queries over the cached analytics DataFrames."""

import pandas as pd

from matchmind.metrics.turning import window_stats


def get_window_stats(
    timeline: pd.DataFrame,
    events: pd.DataFrame,
    from_minute: int = 0,
    to_minute: int = 130,
    period: int | None = None,
) -> dict:
    """Aggregate a clock window and return strongest event evidence."""
    rows = timeline[timeline["minute"].between(from_minute, to_minute)]
    actions = events[events["minute"].between(from_minute, to_minute)]
    if period is not None:
        rows = rows[rows["period"] == period]
        actions = actions[actions["period"] == period]
    key = actions.sort_values("xg", ascending=False).head(4)["id"].tolist()
    return {
        "from_minute": from_minute,
        "to_minute": to_minute,
        "period": period,
        "stats": window_stats(rows),
        "event_ids": key,
    }


def get_player_rankings(
    players: pd.DataFrame,
    events: pd.DataFrame,
    sort: str = "vaep",
    team: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Rank progressors by actual progressive distance, or VAEP/creation/defending."""
    rows = players.to_dict("records")
    if team:
        rows = [p for p in rows if p["team"] == team]

    def score(player: dict) -> float:
        if sort == "progression":
            return player["progression"]["distance"]
        if sort == "defending":
            return player["vaep_def"]
        if sort == "creation":
            return player["vaep_off"]
        return player["vaep"]

    ranked = sorted(rows, key=score, reverse=True)[:limit]
    for p in ranked:
        own = events[events["player_id"] == p["player_id"]].copy()
        if sort == "progression":
            own = own[
                own["type"].isin(("pass", "cross", "carry"))
                & (own["result"] == "success")
            ].copy()
            own["gain"] = (own["end_x"] - own["x"]).where(
                own["team"] == "home", own["x"] - own["end_x"]
            )
            own = own.sort_values("gain", ascending=False)
        else:
            own = own.sort_values("vaep", ascending=False)
        p["event_ids"] = own.head(3)["id"].tolist()
    return ranked
