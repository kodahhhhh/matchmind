"""Resolution audit, historical price windows, and conservative clock alignment."""

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from matchmind.backtest.common import CachedClient, catalogue, output, root, save
from matchmind.backtest.fetch import ALIASES, normalize, relevant


def supplemental(client: CachedClient) -> None:
    found = json.loads((output() / "polymarket_discovery.json").read_text())
    pairs = {(d["match"]["match_id"], d["event"]["id"]) for d in found}
    cats = [m for m in catalogue() if m["demo"] and m["season"] in ("2022", "2024")]
    audit = []
    for query in ["Euro 2024", "Copa America 2024", "World Cup 2022"]:
        seen = set()
        for page in range(1, 21):
            response = client.json(
                "polymarket",
                "https://gamma-api.polymarket.com/public-search",
                q=query,
                events_status="closed",
                limit_per_type=100,
                page=page,
            )
            events = response.get("events", [])
            new = [e for e in events if e["id"] not in seen]
            seen.update(e["id"] for e in events)
            for e in new:
                for m in cats:
                    if (m["match_id"], e["id"]) not in pairs and relevant(e, m):
                        full = client.json(
                            "polymarket",
                            f"https://gamma-api.polymarket.com/events/{e['id']}",
                        )
                        found.append({"match": m, "event": full})
                        pairs.add((m["match_id"], e["id"]))
            if not new or not response.get("pagination", {}).get("hasMore"):
                break
        audit.append(
            {
                "query": query,
                "pages": page,
                "unique_events": len(seen),
                "has_more": response.get("pagination", {}).get("hasMore", False),
            }
        )
        print("Supplemental discovery", audit[-1], flush=True)
    save(output() / "polymarket_discovery.json", found)
    save(output() / "polymarket_supplemental_audit.json", audit)


def archive_discovery(client: CachedClient) -> None:
    """Paginate date-bounded event archives, independently of fuzzy search."""
    found = json.loads((output() / "polymarket_discovery.json").read_text())
    pairs = {(d["match"]["match_id"], d["event"]["id"]) for d in found}
    cats = [m for m in catalogue() if m["demo"] and m["match_date"]]
    audit = []
    windows = [
        ("2015-08-01", "2016-06-01", None),
        ("2022-11-19", "2022-12-28", None),
        ("2023-07-01", "2024-06-13", 1),
        ("2024-06-13", "2024-07-17", 1),
    ]
    for start, end, tag in windows:
        count = 0
        for offset in range(0, 50000, 100):
            params = dict(
                closed="true",
                limit=100,
                offset=offset,
                end_date_min=start + "T00:00:00Z",
                end_date_max=end + "T00:00:00Z",
            )
            if tag:
                params["tag_id"] = tag
            events = client.json(
                "polymarket", "https://gamma-api.polymarket.com/events", **params
            )
            count += len(events)
            for event in events:
                for match in cats:
                    key = (match["match_id"], event["id"])
                    if key not in pairs and relevant(event, match):
                        found.append({"match": match, "event": event})
                        pairs.add(key)
            if len(events) < 100:
                break
        audit.append(
            {
                "start": start,
                "end": end,
                "tag": tag,
                "events": count,
                "exhausted": len(events) < 100,
            }
        )
        print("Archive discovery", audit[-1], flush=True)
    save(output() / "polymarket_discovery.json", found)
    save(output() / "polymarket_archive_audit.json", audit)


def array(value: str | list) -> list:
    return json.loads(value) if isinstance(value, str) else value


def outcome(market: dict, match: dict) -> str | None:
    question = normalize(market["question"])
    if not question.startswith("will "):
        return None
    if "draw" in question and "match" in question:
        return "draw"
    for side in ("home", "away"):
        names = ALIASES.get(match[side]["name"], [match[side]["name"]])
        if any(
            re.match(
                r"^will (?:the )?" + re.escape(normalize(name)) + r"\s+(win|beat)\b",
                question,
            )
            for name in names
        ):
            return side
    return None


def scheduled(match: dict, event: dict) -> tuple[int | None, dict]:
    """Cross-check source clocks; do not silently assume StatsBomb is venue local."""
    starts = [
        m.get("gameStartTime") for m in event["markets"] if m.get("gameStartTime")
    ]
    evidence = {
        "catalogue_date": match["match_date"],
        "catalogue_kickoff": match["kick_off"],
    }
    if not starts:
        return None, {
            **evidence,
            "reason": "No independent scheduled UTC kickoff in market metadata",
        }
    utc = datetime.fromisoformat(starts[0].replace("Z", "+00:00"))
    native = datetime.fromisoformat(f"{match['match_date']}T{match['kick_off']}")
    # Euro and Copa catalogue clocks demonstrably equal UTC market start clocks.
    # Qatar final differs by two hours, and is excluded on resolution rules anyway.
    zones = ["UTC"]
    if match["competition"] == "UEFA Euro":
        zones += ["Europe/Berlin"]
    elif match["competition"] == "FIFA World Cup":
        zones += ["Asia/Qatar", "Europe/Athens"]
    else:
        zones += [
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Los_Angeles",
        ]
    candidates = {
        z: abs(native.replace(tzinfo=ZoneInfo(z)).timestamp() - utc.timestamp())
        for z in zones
    }
    best = min(candidates, key=candidates.get)
    evidence.update(
        market_start=utc.isoformat(),
        clock_interpretation=best,
        zone_errors_seconds=candidates,
    )
    if candidates[best] > 300:
        return None, {
            **evidence,
            "reason": "Scheduled clocks disagree by more than five minutes",
        }
    return int(utc.timestamp()), evidence


def histories(client: CachedClient) -> None:
    discovered = json.loads((output() / "polymarket_discovery.json").read_text())
    accepted, audit = [], []
    for d in discovered:
        match, event = d["match"], d["event"]
        kickoff, evidence = scheduled(match, event)
        row = {
            "match_id": match["match_id"],
            "event_id": event["id"],
            "title": event["title"],
            "volume": float(event.get("volume", 0)),
            "clock": evidence,
            "markets": [],
        }
        markets = {}
        for m in event["markets"]:
            description = m.get("description", "")
            side = outcome(m, match)
            reason = None
            if array(m.get("outcomes", "[]")) != ["Yes", "No"] or side is None:
                reason = "Not a binary regulation 1X2 outcome"
            elif any(
                phrase in description.lower()
                for phrase in [
                    "includes regular time, extra time",
                    "advances to",
                    "advance to",
                ]
            ):
                reason = "Qualification / extra-time resolution"
            elif not ("90 minutes" in description or match["stage"] == "Group Stage"):
                reason = "Regulation-only resolution not explicit"
            if kickoff is None:
                reason = reason or "Unverified scheduled clock"
            row["markets"].append(
                {
                    "id": m["id"],
                    "question": m["question"],
                    "description": description,
                    "outcome": side,
                    "included": reason is None,
                    "reason": reason,
                }
            )
            if reason:
                continue
            if side in markets:
                raise ValueError(f"Duplicate outcome mapping: {event['id']} {side}")
            tokens = array(m["clobTokenIds"])
            prices = {}
            for binary, token in zip(["YES", "NO"], tokens, strict=True):
                prices[binary] = client.json(
                    "polymarket",
                    "https://clob.polymarket.com/prices-history",
                    market=token,
                    startTs=kickoff - 3600,
                    endTs=kickoff + 5 * 3600,
                    fidelity=1,
                ).get("history", [])
            markets[side] = {
                "id": m["id"],
                "prices": prices,
                "resolved": float(array(m["outcomePrices"])[0]),
                "description": description,
                "volume": float(m.get("volume", 0)),
            }
        audit.append(row)
        if markets:
            accepted.append(
                {
                    "match": match,
                    "event_id": event["id"],
                    "market_url": f"https://polymarket.com/event/{event['slug']}",
                    "kickoff": kickoff,
                    "clock": evidence,
                    "volume": row["volume"],
                    "markets": markets,
                }
            )
        save(output() / "polymarket_resolution_audit.json", audit)
        save(output() / "polymarket_histories.json", accepted)
        if len(audit) % 10 == 0:
            print(
                "Market histories",
                len(audit),
                "/",
                len(discovered),
                "eligible events",
                len(accepted),
                flush=True,
            )


def last_price(
    history: list[dict], timestamp: float, max_age: float = 90
) -> float | None:
    """Strict backward as-of, never interpolate or borrow a future trade."""
    eligible = [
        p for p in history if p["t"] < timestamp and timestamp - p["t"] <= max_age
    ]
    return float(max(eligible, key=lambda p: p["t"])["p"]) if eligible else None


def match_goals(match: dict) -> tuple[list[dict], float]:
    events = json.loads(
        (root() / f"raw/statsbomb/data/events/{match['native_id']}.json").read_text()
    )
    goals = []
    first_length = max(
        e["minute"] * 60 + e["second"] for e in events if e["period"] == 1
    )
    for e in events:
        if e["period"] > 2:
            continue
        own = e["type"]["name"] == "Own Goal Against"
        if own or (
            e["type"]["name"] == "Shot" and e["shot"]["outcome"]["name"] == "Goal"
        ):
            side = "home" if e["team"]["id"] == match["home"]["id"] else "away"
            if own:
                side = "away" if side == "home" else "home"
            goals.append(
                {
                    "period": e["period"],
                    "seconds": e["minute"] * 60 + e["second"],
                    "side": side,
                }
            )
    return goals, first_length


def align(item: dict) -> dict:
    """Goal-based clock QA only. No probabilities, labels or P&L choose offsets.

    Strict acceptance: corroborating score-direction price jumps in BOTH halves;
    goal-free halves cannot be verified and the match is excluded. Halftime is
    separately fitted; a single minute-offset across both halves is invalid.
    """
    goals, first_length = match_goals(item["match"])
    evidence = {
        "match_id": item["match"]["match_id"],
        "aligned": False,
        "goals": goals,
        "kickoff": item["kickoff"],
        "period_offsets": {},
        "goal_checks": [],
    }
    for period in (1, 2):
        selected = [
            g for g in goals if g["period"] == period and g["side"] in item["markets"]
        ]
        if not selected:
            evidence["reason"] = (
                f"No usable goal in period {period} to verify the clock"
            )
            return evidence
        # Map displayed match-clock seconds to UTC: add first-half stoppage and
        # interval.
        base = 0 if period == 1 else first_length - 2700 + 15 * 60
        checks = []
        for goal in selected:
            hist = sorted(
                item["markets"][goal["side"]]["prices"]["YES"], key=lambda p: p["t"]
            )
            expected = item["kickoff"] + goal["seconds"] + base
            jumps = []
            for a, b in zip(hist, hist[1:], strict=False):
                if (
                    0 < b["t"] - a["t"] <= 90
                    and -180 <= b["t"] - expected <= 300
                    and b["p"] - a["p"] >= 0.04
                ):
                    jumps.append((b["p"] - a["p"], b["t"]))
            if not jumps:
                continue
            _, at = max(jumps)
            checks.append(
                {
                    "period": period,
                    "goal_seconds": goal["seconds"],
                    "side": goal["side"],
                    "jump_timestamp": at,
                    "offset_seconds": at - item["kickoff"] - goal["seconds"],
                }
            )
        if not checks:
            evidence["reason"] = (
                f"No clear goal-direction price jump in period {period}"
            )
            return evidence
        offsets = np.array([c["offset_seconds"] for c in checks])
        if offsets.max() - offsets.min() > 120:
            evidence["reason"] = f"Inconsistent goal offsets in period {period}"
            return evidence
        # Price timestamps lag events. Use the upper edge (latest observation) to
        # ensure post-goal information cannot meet pre-goal prices. Still embargo goals.
        offset = float(offsets.max())
        evidence["period_offsets"][str(period)] = offset
        evidence["goal_checks"].extend(checks)
    evidence["aligned"] = True
    evidence["offset_seconds"] = evidence["period_offsets"]["1"]
    evidence["reason"] = (
        "Both halves have score-direction goal jumps; <=120s within-"
        "half dispersion; goal neighborhoods excluded."
    )
    return evidence


def fetch() -> None:
    client = CachedClient()
    supplemental(client)
    archive_discovery(client)
    histories(client)
