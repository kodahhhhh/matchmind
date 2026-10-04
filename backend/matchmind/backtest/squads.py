"""Build auditable historical squad inputs from cached CC0 tables and SB lineups."""

import json
from collections import defaultdict
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from matchmind.backtest.common import catalogue, output, root, save
from matchmind.backtest.fetch import normalize
from matchmind.models.squad import (
    contrasts,
    historical_value,
    live_strength,
    team_features,
)

ALIASES = {
    "AS Roma": "Associazione Sportiva Roma",
    "Lyon": "Olympique Lyon",
    "Rennes": "Stade Rennais FC",
    "Stade Malherbe Caen": "SM Caen",
    "Athletic Club": "Athletic Bilbao",
    "RC Deportivo La Coruña": "Deportivo de La Coruña",
    "Bayer Leverkusen": "Bayer 04 Leverkusen",
    "Hertha Berlin": "Hertha BSC",
    "Ingolstadt": "FC Ingolstadt 04",
    "Hoffenheim": "TSG 1899 Hoffenheim",
    "FC Heidenheim": "1. Fußballclub Heidenheim 1846",
    "FSV Mainz 05": "1.FSV Mainz 05",
    "Internazionale": "Inter Milan",
    "Deportivo La Coruna": "Deportivo de La Coruña",
    "PSG": "Paris Saint-Germain",
    "Sporting Gijon": "Sporting Gijón",
    "Rayo Vallecano": "Rayo Vallecano",
    "Atletico Madrid": "Atlético de Madrid",
    "Espanyol": "RCD Espanyol Barcelona",
    "Celta Vigo": "Celta de Vigo",
    "Las Palmas": "UD Las Palmas",
    "Malaga": "Málaga CF",
    "Real Betis": "Real Betis Balompié",
    "Real Valladolid": "Real Valladolid CF",
    "Alaves": "Deportivo Alavés",
    "Leganes": "CD Leganés",
    "Paris Saint-Germain": "Paris Saint-Germain",
    "Manchester United": "Manchester United",
    "Czech Republic": "Czech Republic",
    "Turkey": "Türkiye",
    "United States": "United States",
}


def similarity(a: str, b: str) -> float:
    a, b = normalize(ALIASES.get(a, a)).replace(" ", ""), normalize(b).replace(" ", "")
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 5 and (a in b or b in a):
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def read_tables() -> dict[str, pd.DataFrame]:
    columns = {
        "players": ["player_id", "name", "country_of_citizenship", "date_of_birth"],
        "player_valuations": ["player_id", "date", "market_value_in_eur"],
        "games": [
            "game_id",
            "date",
            "home_club_id",
            "away_club_id",
            "home_club_name",
            "away_club_name",
            "competition_type",
        ],
        "game_lineups": [
            "game_id",
            "date",
            "player_id",
            "club_id",
            "player_name",
            "type",
            "number",
        ],
        "appearances": [
            "game_id",
            "date",
            "player_id",
            "player_club_id",
            "minutes_played",
        ],
    }
    result = {}
    for name, cols in columns.items():
        cache = output() / f"squad_source_{name}.parquet"
        if cache.exists():
            frame = pd.read_parquet(cache)
        else:
            frame = pd.read_csv(
                root() / f"raw/players/transfermarkt/{name}.csv.gz",
                usecols=cols,
                low_memory=False,
            )
            for col in ("date", "date_of_birth"):
                if col in frame:
                    frame[col] = pd.to_datetime(frame[col], errors="coerce")
            frame.to_parquet(cache, index=False)
        result[name] = frame
        print("Squad source", name, len(frame), flush=True)
    return result


def match_games(matches: list[dict], games: pd.DataFrame) -> tuple[dict, list]:
    by_date = {str(date.date()): group for date, group in games.groupby("date")}
    joined, audit = {}, []
    for match in matches:
        candidates = by_date.get(match["match_date"])
        ranked = []
        if candidates is not None:
            for game in candidates.itertuples():
                h = similarity(match["home"]["name"], str(game.home_club_name))
                a = similarity(match["away"]["name"], str(game.away_club_name))
                ranked.append((min(h, a), (h + a) / 2, game))
        ranked.sort(key=lambda v: v[:2], reverse=True)
        accepted = bool(
            ranked
            and ranked[0][0] >= 0.7
            and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= 0.12)
        )
        if accepted:
            joined[match["native_id"]] = ranked[0][2]
        audit.append(
            {
                "match_id": match["match_id"],
                "competition": match["competition"],
                "season": match["season"],
                "date": match["match_date"],
                "home": match["home"]["name"],
                "away": match["away"]["name"],
                "matched": accepted,
                "candidate": {
                    "home": ranked[0][2].home_club_name,
                    "away": ranked[0][2].away_club_name,
                    "score": ranked[0][0],
                    "game_id": ranked[0][2].game_id,
                }
                if ranked
                else None,
            }
        )
    return joined, audit


def player_map() -> dict[int, int]:
    path = root() / "processed/players/player_map.parquet"
    if not (path.parent / "_READY").exists():
        print("W11 _READY absent; international map deferred", flush=True)
        return {}
    frame = pd.read_parquet(path)
    print("W11 map columns", list(frame), flush=True)
    sb = next(
        c for c in ("sb_player_id", "statsbomb_player_id", "player_id") if c in frame
    )
    tm = next(c for c in ("tm_player_id", "transfermarkt_player_id") if c in frame)
    frame = frame[frame.confidence >= 0.8].dropna(subset=[sb, tm])
    if frame[sb].duplicated().any():
        raise ValueError("Ambiguous W11 mapping")
    return dict(zip(frame[sb].astype(int), frame[tm].astype(int), strict=True))


def build() -> None:
    tables = read_tables()
    matches = [dict(m) for m in catalogue() if m["training"]]
    dates = {
        m["native_id"]: m["match_date"]
        for m in json.loads((output() / "bookmaker_1516.json").read_text())
    }
    for match in matches:
        match["match_date"] = match["match_date"] or dates.get(match["native_id"])
    joined, audit = match_games(matches, tables["games"])
    save(output() / "squad_match_audit.json", audit)
    mapping = player_map()
    births = tables["players"].set_index("player_id").date_of_birth.to_dict()
    # Reject duplicate player/date snapshots rather than choose an arbitrary value.
    vals = tables["player_valuations"].drop_duplicates(
        ["player_id", "date", "market_value_in_eur"]
    )
    if vals.duplicated(["player_id", "date"]).any():
        raise ValueError("Conflicting valuation snapshots")
    valuations = {
        pid: (g.date.to_numpy(), g.market_value_in_eur.to_numpy())
        for pid, g in vals.sort_values("date").groupby("player_id")
    }
    lineups = tables["game_lineups"].drop_duplicates(
        ["game_id", "club_id", "player_id"]
    )
    by_game = {gid: group for gid, group in lineups.groupby("game_id")}
    previous = defaultdict(list)
    starts = lineups[lineups.type == "starting_lineup"]
    for (club, date, _gid), group in starts.groupby(
        ["club_id", "date", "game_id"], sort=True
    ):
        previous[club].append((date, group.player_id.tolist()))
    appearances = tables["appearances"]
    national_ids = set(
        tables["games"].loc[
            tables["games"].competition_type == "national_team_competition", "game_id"
        ]
    )
    caps = {
        pid: np.sort(g.date.to_numpy())
        for pid, g in appearances[
            (appearances.game_id.isin(national_ids)) & (appearances.minutes_played > 0)
        ].groupby("player_id")
    }
    club_apps = appearances[~appearances.game_id.isin(national_ids)].sort_values("date")
    histories = {
        pid: g[["date", "player_club_id"]] for pid, g in club_apps.groupby("player_id")
    }
    prematch, live, coverage = [], [], []
    for index, match in enumerate(matches):
        date = pd.Timestamp(match["match_date"]) if match["match_date"] else pd.NaT
        events = json.loads(
            (
                root() / f"raw/statsbomb/data/events/{match['native_id']}.json"
            ).read_text()
        )
        starters = {
            e["team"]["id"]: e["tactics"]["lineup"]
            for e in events
            if e["type"]["name"] == "Starting XI"
        }
        sb_lineups = json.loads(
            (
                root() / f"raw/statsbomb/data/lineups/{match['native_id']}.json"
            ).read_text()
        )
        game = joined.get(match["native_id"])
        tm_lineups = by_game.get(game.game_id) if game is not None else None
        international = match["competition"] in {
            "FIFA World Cup",
            "UEFA Euro",
            "Copa America",
            "African Cup of Nations",
            "FIFA U20 World Cup",
        }
        sides, sb_values = {}, {}
        for side in ("home", "away"):
            tid = match[side]["id"]
            sb_xi = [p["player"]["id"] for p in starters.get(tid, [])]
            announced = next(
                (t["lineup"] for t in sb_lineups if t["team_id"] == tid), []
            )
            local_map = dict(mapping)
            club = getattr(game, f"{side}_club_id") if game else None
            group = (
                tm_lineups[tm_lineups.club_id == club]
                if tm_lineups is not None
                else None
            )
            if not international and group is not None:
                # Same dated game and side, unique shirt number plus a name check.
                for player in announced:
                    numbered = group[
                        pd.to_numeric(group.number, errors="coerce")
                        == player["jersey_number"]
                    ]
                    if len(numbered) == 1:
                        candidate = numbered.iloc[0]
                        name = player.get("player_nickname") or player["player_name"]
                        if similarity(name, candidate.player_name) >= 0.45:
                            local_map[player["player_id"]] = int(candidate.player_id)
                xi = (
                    group.loc[group.type == "starting_lineup", "player_id"]
                    .astype(int)
                    .tolist()
                )
                bench = (
                    group.loc[group.type == "substitutes", "player_id"]
                    .astype(int)
                    .tolist()
                )
            else:
                xi = [local_map[p] for p in sb_xi if p in local_map]
                bench = [
                    local_map[p["player_id"]]
                    for p in announced
                    if p["player_id"] not in sb_xi and p["player_id"] in local_map
                ]
            past = [
                (d, ids)
                for d, ids in previous.get(club, [])
                if pd.notna(date) and d < date
            ]
            ids = set(xi + bench + [p for _, ps in past[-5:] for p in ps]) | {
                local_map[p["player_id"]]
                for p in announced
                if p["player_id"] in local_map
            }
            values, cap_counts, signings = {}, {}, {}
            for pid in ids:
                if pd.notna(date) and pid in valuations:
                    times, amounts = valuations[pid]
                    amount = historical_value(times, amounts, date)
                    if np.isfinite(amount):
                        values[pid] = amount
                cap_counts[pid] = (
                    int(
                        np.searchsorted(
                            caps.get(pid, np.array([], dtype="datetime64[ns]")),
                            date.to_datetime64(),
                            side="left",
                        )
                    )
                    if pd.notna(date)
                    else 0
                )
                if not international and pid in histories and pd.notna(date):
                    history = histories[pid]
                    history = history[history.date < date]
                    at_club = history[history.player_club_id == club]
                    if len(at_club):
                        first = at_club.date.min()
                        # Infer signings only with an earlier different club.
                        other = history[
                            (history.date < first) & (history.player_club_id != club)
                        ]
                        if len(other) or (date - first).days >= 180:
                            signings[pid] = (date - first).days < 180
            for player in announced:
                pid = local_map.get(player["player_id"])
                if pid in values:
                    sb_values[player["player_id"]] = values[pid]
            sides[side] = team_features(
                xi,
                bench,
                date,
                values,
                births,
                [ids for _, ids in past],
                cap_counts,
                signings,
            )
            coverage.append(
                {
                    "match_id": match["match_id"],
                    "competition": match["competition"],
                    "season": match["season"],
                    "side": side,
                    "tm_game": game.game_id if game else None,
                    "mapped_xi": len(xi),
                    "valued_xi": round(sides[side]["valuation_coverage"] * 11),
                    "live_valued_xi": sum(p in sb_values for p in sb_xi),
                    "international": international,
                }
            )
        prematch.append(
            {"match_id": match["match_id"], **contrasts(sides["home"], sides["away"])}
        )
        boundaries = pd.DataFrame(
            [
                (p, m)
                for p in (1, 2)
                for m in range(0 if p == 1 else 45, 46 if p == 1 else 91)
            ],
            columns=["period", "minute"],
        )
        frame = live_strength(events, sb_values, boundaries)
        # Normalize raw Starting XI order to the catalogue home team.
        if (
            next(e for e in events if e["type"]["name"] == "Starting XI")["team"]["id"]
            != match["home"]["id"]
        ):
            frame["pitch_log_value_diff"] *= -1
        frame["match_id"] = match["match_id"]
        live.append(frame)
        if index % 200 == 0:
            print("Squad matches", index, "/", len(matches), flush=True)
    pd.DataFrame(prematch).to_parquet(output() / "squad_prematch.parquet", index=False)
    pd.concat(live, ignore_index=True).to_parquet(
        output() / "squad_live.parquet", index=False
    )
    pd.DataFrame(coverage).to_parquet(output() / "squad_coverage.parquet", index=False)
    save(
        output() / "squad_provenance.json",
        {
            "w11_ready": bool(mapping),
            "w11_mapped_players": len(mapping),
            "valuation_cutoff": "strictly earlier date; no current market values",
            "caps": "observed prior TM international appearances, not lifetime caps",
            "new_signings": "prior club appearances only, never snapshot current club",
            "matched_games": len(joined),
            "matches": len(matches),
        },
    )


if __name__ == "__main__":
    build()
