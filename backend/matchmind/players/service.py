"""Read precomputed all-corpus summaries; no network or model inference at request time.

Underrated score = (market-value rank - metric rank) / (eligible players - 1).
Both ranks are descending average ranks (ties share rank). A positive score means
performance ranks above price. Missing historical price yields null price/rank/
score. This is a descriptive comparison within selected, uneven StatsBomb data.
"""

import copy
import json
import re
from datetime import date
from functools import lru_cache

import pandas as pd

from matchmind.config import get_settings
from matchmind.players.matching import normalise
from matchmind.players.schemas import Metric


class PlayerNotFound(LookupError):
    """A player or requested player-match is absent from the training corpus."""


@lru_cache(maxsize=1)
def store() -> tuple[dict[int, dict], dict[int, list[dict]], dict, pd.DataFrame]:
    """Load atomically published artifacts once per API process."""
    directory = get_settings().data_dir / "processed/players"
    profiles = pd.read_parquet(directory / "profiles.parquet")
    # JSON conversion normalizes nullable integers, numpy scalars and NaN.
    rows = json.loads(profiles.to_json(orient="records"))
    identities = {r["sb_player_id"]: r for r in rows}
    values = pd.read_parquet(directory / "valuations.parquet")
    histories = {}
    for row in json.loads(
        values.sort_values(["tm_player_id", "date"]).to_json(orient="records")
    ):
        pid = row.pop("tm_player_id")
        histories.setdefault(pid, []).append(row)
    careers = json.loads((directory / "career.json").read_text())
    matches = pd.read_parquet(directory / "matches.parquet")
    return identities, histories, careers, matches


def historical_value(
    valuations: list[dict], as_of: str | None, strict: bool = False
) -> int | None:
    """Latest known value before match day, or on/before season end."""
    if as_of is None:
        return None
    eligible = [
        row
        for row in valuations
        if row["date"] < as_of or (not strict and row["date"] == as_of)
    ]
    return (
        int(max(eligible, key=lambda r: r["date"])["value_eur"]) if eligible else None
    )


def age_at(dob: str | None, match_date: str | None) -> int | None:
    """Completed years on the verified source date; undated matches stay null."""
    if not dob or not match_date:
        return None
    born, played = date.fromisoformat(dob), date.fromisoformat(match_date)
    return (
        played.year - born.year - ((played.month, played.day) < (born.month, born.day))
    )


def get_player_profile(player_id: int, match_id: str | None = None) -> dict:
    """Return the exact profile contract, optionally with historical match context."""
    profiles, histories, careers, matches = store()
    if player_id not in profiles:
        raise PlayerNotFound(f"Player {player_id} has no published profile")
    row = profiles[player_id]
    valuations = histories.get(row["tm_player_id"], [])
    profile = {
        k: row[k]
        for k in (
            "name",
            "short_name",
            "nickname",
            "photo_url",
            "photo_credit",
            "photo_license",
            "date_of_birth",
            "height_cm",
            "foot",
            "position",
            "nationality",
            "current_club",
            "market_value_eur",
            "peak_market_value_eur",
            "caps",
            "match_confidence",
        )
    }
    profile.update(
        {
            "player_id": player_id,
            "in_dataset": row["in_dataset"],
            "sources": row["sources"],
            "transfermarkt_id": row["tm_player_id"],
            "wikidata_id": row["wikidata_qid"],
            "valuations": valuations,
            **copy.deepcopy(
                careers.get(
                    str(player_id),
                    {
                        "career": None,
                        "heatmap": None,
                        "top_moments": [],
                        "matches": [],
                    },
                )
            ),
            "in_match": None,
        }
    )
    if match_id is not None and row["in_dataset"]:
        selected = matches[
            (matches.player_id == player_id) & (matches.match_id == match_id)
        ]
        if selected.empty:
            raise PlayerNotFound(
                "Player did not appear in the requested training match"
            )
        appearance = selected.iloc[0]
        played_date = appearance["date"]
        ranks = (
            matches[matches.match_id == match_id]
            .set_index("player_id")
            .vaep.rank(method="min", ascending=False)
        )
        profile["in_match"] = {
            "age": age_at(row["date_of_birth"], played_date),
            "market_value_eur": historical_value(valuations, played_date, strict=True),
            "minutes": float(appearance.minutes),
            "vaep": float(appearance.vaep),
            "rank_in_match": int(ranks.loc[player_id]),
        }
    return profile


@lru_cache(maxsize=1)
def search_index() -> list[tuple[list[str], list[str], dict]]:
    """Precompute normalized names/results ordered by dataset, then market value."""
    profiles, _, careers, _ = store()
    ranked = sorted(
        profiles.items(),
        key=lambda pair: (
            not pair[1]["in_dataset"],
            -(pair[1]["market_value_eur"] or 0),
            pair[0],
        ),
    )
    results = []
    for pid, row in ranked:
        summary = careers.get(
            str(pid), {"career": {"matches": 0, "vaep_per90": 0}, "matches": []}
        )
        primary = {normalise(row[k]) for k in ("name", "short_name", "nickname")} - {""}
        names = sorted(primary | {normalise(n) for n in row.get("aliases", [])} - {""})
        teams = sorted({m["team"] for m in summary["matches"]})
        if not row["in_dataset"] and row["current_club"]:
            teams = [row["current_club"]]
        results.append(
            (
                names,
                sorted(primary),
                {
                    "player_id": pid,
                    "in_dataset": row["in_dataset"],
                    **{
                        k: row[k]
                        for k in (
                            "name",
                            "short_name",
                            "nationality",
                            "position",
                            "photo_url",
                        )
                    },
                    "teams": teams,
                    "matches": summary["career"]["matches"],
                    "vaep_per90": summary["career"]["vaep_per90"],
                },
            )
        )
    return results


def search_players(query: str, limit: int = 20) -> dict:
    """Search every profile without per-request normalization or career scans."""
    tokens = normalise(query).split()
    index = search_index()
    if not tokens:
        return {"results": [r for _, _, r in index[:limit]]}
    postings = search_postings()
    grams = {
        token[i : i + min(3, len(token))]
        for token in tokens
        for i in range(max(1, len(token) - 2))
    }
    groups = sorted((postings.get(g, set()) for g in grams), key=len)
    candidates = groups[0].intersection(*groups[1:])
    # Rank: matches on a player's real names before alias-only matches (Wikidata
    # aliases include nicknames and jokes), then the precomputed dataset/value order.
    scored = []
    for offset in candidates:
        names, primary, row = index[offset]
        if any(all(token in name for token in tokens) for name in primary):
            scored.append((0, offset, row))
        elif any(all(token in name for token in tokens) for name in names):
            scored.append((1, offset, row))
    scored.sort(key=lambda item: item[:2])
    return {"results": [row for _, _, row in scored[:limit]]}


@lru_cache(maxsize=1)
def search_postings() -> dict[str, set[int]]:
    """A substring index preserves token search while bounding worst-case scans."""
    postings = {}
    for offset, (names, _, _) in enumerate(search_index()):
        grams = {
            name[i : i + width]
            for name in names
            for width in (1, 2, 3)
            for i in range(len(name) - width + 1)
        }
        for gram in grams:
            postings.setdefault(gram, set()).add(offset)
    return postings


def season_end(season: str) -> str:
    """European split season ends June 30; calendar competition ends December 31."""
    years = re.findall(r"\d{4}", season)
    if not years:
        raise ValueError(f"Unrecognized season {season}")
    return f"{years[-1]}-06-30" if len(years) > 1 else f"{years[0]}-12-31"


@lru_cache(maxsize=64)
def leaderboard(
    metric: Metric = "vaep_per90",
    min_minutes: float = 900,
    competition: str | None = None,
    season: str | None = None,
    limit: int = 50,
) -> dict:
    """Compute one weighted row per eligible player, rank before truncating."""
    profiles, histories, _, matches = store()
    frame = matches
    if competition:
        frame = frame[frame.competition == competition]
    if season:
        frame = frame[frame.season == season]
    rows = []
    for pid, group in frame.groupby("player_id"):
        minutes = float(group.minutes.sum())
        if minutes < min_minutes or minutes <= 0 or pid not in profiles:
            continue
        identity = profiles[pid]
        if metric == "vaep_per90":
            value = float(group.vaep.sum()) * 90 / minutes
        elif metric == "prog_per90":
            value = (
                float(group.progressive_passes.sum() + group.progressive_carries.sum())
                * 90
                / minutes
            )
        else:
            value = float(group[metric].sum())
        selected_seasons = sorted(set(group.season))
        cutoff = max(season_end(s) for s in selected_seasons)
        price = historical_value(histories.get(identity["tm_player_id"], []), cutoff)
        teams = list(
            group.groupby("team").minutes.sum().sort_values(ascending=False).index
        )
        rows.append(
            {
                "player_id": int(pid),
                "name": identity["name"],
                "short_name": identity["short_name"],
                "team": " / ".join(teams),
                "competition": competition
                or " / ".join(sorted(set(group.competition))),
                "season": season or " / ".join(selected_seasons),
                "minutes": minutes,
                "value": value,
                "market_value_eur": price,
            }
        )
    if not rows:
        return {"metric": metric, "rows": []}
    result = pd.DataFrame(rows)
    result["metric_rank"] = result.value.rank(ascending=False, method="average")
    result["value_rank"] = result.market_value_eur.rank(
        ascending=False, method="average"
    )
    result["underrated_score"] = (result.value_rank - result.metric_rank) / max(
        len(result) - 1, 1
    )
    result = result.sort_values(["value", "player_id"], ascending=[False, True]).head(
        limit
    )
    return {"metric": metric, "rows": json.loads(result.to_json(orient="records"))}


def analyst_profile(player_id: int, match_id: str) -> dict:
    """Expose computed numbers with explicit real event/sequence evidence labels."""
    from matchmind.analyst.grounding import display_evidence

    result = get_player_profile(player_id, match_id)
    labels = {}
    for moment in result["top_moments"]:
        labels["ev:" + moment["event_id"]] = (
            f"{moment['minute_label']} {result['short_name']}"
        )
        if moment["sequence_id"]:
            labels["seq:" + moment["sequence_id"]] = moment["match_label"]
    result["evidence_labels"] = labels
    result["metric_notes"] = {
        "scope": "Selected StatsBomb training corpus, not full professional career"
        if result["in_dataset"]
        else "Biography and valuations; no observations in the training corpus",
        "values": "Match-held-out xG and VAEP; price strictly before match day"
        if result["in_dataset"]
        else "Published historical market valuations",
        "progression": (
            "Successful passes/carries gaining at least 10 metres toward goal"
        ),
    }
    result["display_numbers"] = display_evidence(result)
    return result
