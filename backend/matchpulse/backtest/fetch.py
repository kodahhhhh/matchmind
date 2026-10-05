"""Allowed public sources only; raw responses are immutable and rate limited."""

import io
import json
import re
import unicodedata
from datetime import datetime

import pandas as pd

from matchpulse.backtest.common import CachedClient, catalogue, output, save

NAMES = {
    "Bayern Munich": "Bayern Munich",
    "Hamburg": "Hamburger SV",
    "Augsburg": "Augsburg",
    "Hertha": "Hertha Berlin",
    "Darmstadt": "Darmstadt 98",
    "Hannover": "Hannover 96",
    "Dortmund": "Borussia Dortmund",
    "M'gladbach": "Borussia Mönchengladbach",
    "Leverkusen": "Bayer Leverkusen",
    "Hoffenheim": "Hoffenheim",
    "Mainz": "FSV Mainz 05",
    "Ingolstadt": "Ingolstadt",
    "Werder Bremen": "Werder Bremen",
    "Schalke 04": "Schalke 04",
    "Stuttgart": "VfB Stuttgart",
    "FC Koln": "FC Köln",
    "Wolfsburg": "Wolfsburg",
    "Ein Frankfurt": "Eintracht Frankfurt",
    "Bochum": "Bochum",
    "Heidenheim": "FC Heidenheim",
    "RB Leipzig": "RB Leipzig",
    "Union Berlin": "Union Berlin",
    "Freiburg": "Freiburg",
}
ALIASES = {
    "United States": ["USA", "United States", "USMNT"],
    "South Korea": ["South Korea", "Korea Republic"],
    "Czech Republic": ["Czech Republic", "Czechia"],
    "Turkey": ["Turkey", "Türkiye", "Turkiye"],
    "Bayer Leverkusen": ["Leverkusen"],
    "Inter Miami": ["Inter Miami", "Miami"],
}


def normalize(text: str) -> str:
    return re.sub(
        r"[^a-z0-9 ]",
        "",
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower(),
    )


def bookmaker(client: CachedClient) -> dict:
    report = {}
    cats = catalogue()
    for season, code in [("2015/2016", "1516"), ("2023/2024", "2324")]:
        url = f"https://www.football-data.co.uk/mmz4281/{code}/D1.csv"
        response = client.get("football-data", url)
        if response["status"] != 200 or not response["body"].strip():
            response = client.get("football-data", url.replace("https:", "http:"))
        rows = pd.read_csv(io.StringIO(response["body"]))
        lookup = {
            (m["home"]["name"], m["away"]["name"]): m
            for m in cats
            if m["competition_id"] == 9 and m["season"] == season
        }
        joined, unmatched = [], []
        for i, r in rows.iterrows():
            key = (NAMES.get(r.HomeTeam, r.HomeTeam), NAMES.get(r.AwayTeam, r.AwayTeam))
            match = lookup.get(key)
            if match is None:
                unmatched.append({"home": r.HomeTeam, "away": r.AwayTeam})
                continue
            if (int(r.FTHG), int(r.FTAG)) != (match["home_score"], match["away_score"]):
                raise ValueError(f"Score mismatch {match['match_id']}")
            joined.append(
                {
                    **match,
                    "match_date": pd.to_datetime(r.Date, dayfirst=True)
                    .date()
                    .isoformat(),
                    "round": i // 9 + 1,
                    "opening": [float(r[c]) for c in ["PSH", "PSD", "PSA"]],
                    "closing": [float(r[c]) for c in ["PSCH", "PSCD", "PSCA"]],
                }
            )
        missing = sorted(
            set(m["match_id"] for m in lookup.values())
            - set(m["match_id"] for m in joined)
        )
        report[season] = {
            "csv_rows": len(rows),
            "matched": len(joined),
            "unmatched_csv": unmatched,
            "unmatched_catalogue": missing,
            "url": url,
        }
        save(output() / f"bookmaker_{code}.json", joined)
    save(output() / "bookmaker_coverage.json", report)
    return report


def relevant(event: dict, match: dict) -> bool:
    title = normalize(event.get("title", ""))
    if not all(
        any(
            normalize(a) in title
            for a in ALIASES.get(match[s]["name"], [match[s]["name"]])
        )
        for s in ["home", "away"]
    ):
        return False
    date = match["match_date"]
    text = json.dumps(event)
    # Require calendar-date evidence, not just a repeating country pairing.
    return date in text or (
        date and datetime.fromisoformat(date).strftime("%B %-d, %Y") in text
    )


def polymarket(client: CachedClient) -> dict:
    matches = [
        m
        for m in catalogue()
        if m["demo"] and m["match_date"] and m["season"] != "2015/2016"
    ]
    discovered, checks = [], []
    for i, match in enumerate(matches):
        home, away = match["home"]["name"], match["away"]["name"]
        q = f"{ALIASES.get(home, [home])[0]} {ALIASES.get(away, [away])[0]}"
        events = []
        error = None
        try:
            page = 1
            while True:
                response = client.json(
                    "polymarket",
                    "https://gamma-api.polymarket.com/public-search",
                    q=q,
                    events_status="closed",
                    limit_per_type=100,
                    page=page,
                )
                events.extend(response.get("events", []))
                if not response.get("pagination", {}).get("hasMore"):
                    break
                page += 1
                if page > 10:
                    raise RuntimeError("Search pagination exceeded 10 pages")
        except (RuntimeError, ValueError) as exc:
            error = str(exc)
        found = [e for e in events if relevant(e, match)]
        for event in found:
            # Read complete event and every resolution description.
            full = client.json(
                "polymarket", f"https://gamma-api.polymarket.com/events/{event['id']}"
            )
            discovered.append({"match": match, "event": full})
        checks.append(
            {
                "match_id": match["match_id"],
                "query": q,
                "events": [e["id"] for e in found],
                "error": error,
            }
        )
        if i % 10 == 0:
            print(
                "Polymarket discovery",
                i,
                "/",
                len(matches),
                "events",
                len(discovered),
                flush=True,
            )
        save(output() / "polymarket_discovery.json", discovered)
        save(output() / "polymarket_search_audit.json", checks)
    return {
        "searched": len(checks),
        "events": len(discovered),
        "matches": len({d["match"]["match_id"] for d in discovered}),
        "errors": sum(c["error"] is not None for c in checks),
    }


def kalshi(client: CachedClient) -> dict:
    rows, cursor, requests = [], "", []
    while True:
        params = {"limit": 1000, "status": "settled", "max_close_ts": 1725148800}
        if cursor:
            params["cursor"] = cursor
        response = client.json(
            "kalshi", "https://api.elections.kalshi.com/trade-api/v2/markets", **params
        )
        rows.extend(response.get("markets", []))
        requests.append(params)
        cursor = response.get("cursor", "")
        if not cursor:
            break
    sports = [
        r
        for r in rows
        if re.search(
            r"soccer|football|world cup|copa|euro 2024|bundesliga",
            r.get("title", "") + " " + r.get("ticker", ""),
            re.I,
        )
    ]
    series = client.json(
        "kalshi",
        "https://api.elections.kalshi.com/trade-api/v2/series",
        category="Sports",
    )
    archive_checks = []
    for ticker in [
        "KXWCGAME",
        "KXUEFAGAME",
        "KXCOPAAMERICA",
        "KXUEFAEURO",
        "KXBUNDESLIGAGAME",
        "KXMLSGAME",
        "KXWC",
        "KXMENWORLDCUP",
    ]:
        archived, cursor = [], ""
        while True:
            params = {"series_ticker": ticker, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            data = client.json(
                "kalshi",
                "https://api.elections.kalshi.com/trade-api/v2/historical/markets",
                **params,
            )
            archived.extend(data.get("markets", []))
            cursor = data.get("cursor", "")
            if not cursor:
                break
        dates = [m["close_time"] for m in archived if m.get("close_time")]
        archive_checks.append(
            {
                "series": ticker,
                "rows": len(archived),
                "earliest_close": min(dates) if dates else None,
                "pre_september_2024": sum(d < "2024-09-01" for d in dates),
            }
        )
        print("Kalshi archived series", archive_checks[-1], flush=True)
    report = {
        "matches": 0,
        "historical_rows": len(rows),
        "candidate_rows": sports,
        "requests": requests,
        "sports_series_returned": len(series.get("series", [])),
        "archived_series_checks": archive_checks,
        "notes": (
            "No matching demo markets in the current settled-market query "
            "through 2024-09-01 or eight relevant archived football series. "
            "Archive evidence covers 3,081 contracts, all closing in 2025 or later. "
            "Coverage is limited to the public archive and current series taxonomy."
        ),
    }
    save(output() / "kalshi_coverage.json", report)
    return report


def fetch() -> None:
    client = CachedClient()
    print("Bookmaker coverage", bookmaker(client), flush=True)
    print("Kalshi coverage", kalshi(client), flush=True)
    print("Polymarket coverage", polymarket(client), flush=True)
