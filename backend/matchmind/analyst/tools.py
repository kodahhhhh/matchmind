"""Sol's fixed tool schemas and orchestration over pure metrics functions."""

import asyncio

import pandas as pd

from matchmind.analyst.commentary_store import get_commentary
from matchmind.analyst.grounding import display_evidence
from matchmind.api.counterfactual import run_counterfactual
from matchmind.api.repository import bundle
from matchmind.api.search import search_moments
from matchmind.metrics.match import clock_label
from matchmind.metrics.tools import get_player_rankings, get_window_stats


def tool_schema(
    name: str, description: str, properties: dict, required: list[str] | None = None
) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


INT = {"type": "integer"}
SIDE = {"type": "string", "enum": ["home", "away"]}
TOOLS = [
    tool_schema(
        "get_player_profile",
        "Player identity, historical value/age in this match, all-corpus career "
        "metrics and top moments with real evidence IDs. Numbers come only from "
        "this output. Corpus coverage is selected, not a complete career.",
        {"player_id": INT},
        ["player_id"],
    ),
    tool_schema(
        "get_window_stats",
        "Compare match-clock windows. Includes possession pass share, "
        "tilt, xG, shots, momentum and evidence IDs.",
        {"from_minute": INT, "to_minute": INT, "period": INT},
    ),
    tool_schema(
        "get_events",
        "Get actions and goal/sub/card markers. types may include sub, "
        "goal, card, shot, pass or carry.",
        {
            "types": {"type": "array", "items": {"type": "string"}},
            "team": SIDE,
            "from_minute": INT,
            "to_minute": INT,
            "limit": INT,
        },
    ),
    tool_schema(
        "get_top_sequences",
        "Most dangerous possession sequences, positive VAEP/threat gain by "
        "possession owner.",
        {"limit": INT, "team": SIDE},
    ),
    tool_schema(
        "get_player_rankings",
        "Player value, progression, defending and creation with action "
        "IDs. progression ranks progressive distance.",
        {
            "sort": {
                "type": "string",
                "enum": ["vaep", "progression", "defending", "creation"],
            },
            "team": SIDE,
            "limit": INT,
        },
    ),
    tool_schema(
        "find_turning_points",
        "Period-aware Binseg momentum change points, before/after stats "
        "and key goals/shots.",
        {},
    ),
    tool_schema(
        "run_counterfactual",
        "Modelled hypothetical for a goal, substitution or red card. Lead with "
        "`result`: probabilities of how normal time (or extra time) ends, real "
        "state (`factual`) versus changed (`modelled`), from an actual-goals "
        "model; `scoring_chance` is each side's chance to score in the next 15 "
        "minutes. For chance quality compare `modelled` with `factual`; "
        "`effect` is their median difference and `negligible` flags no real "
        "change. lineup_change names the player put back and both ratings. "
        "Never compare `modelled` with `actual`. Not causal certainty.",
        {
            "event_id": {"type": "string"},
            "change": {
                "type": "string",
                "enum": ["remove_goal", "no_sub", "remove_red_card"],
            },
        },
        ["event_id", "change"],
    ),
    tool_schema(
        "shot_alternatives",
        "Modelled pass-instead-of-shot options for one non-penalty shot event: "
        "each teammate's pass completion chance, follow-up value and the "
        "shot's own xG, plus a Python comparison. Use get_events with "
        "types=['shot'] first to find the shot event ID.",
        {"event_id": {"type": "string"}},
        ["event_id"],
    ),
    tool_schema(
        "search_moments",
        "Hybrid commentary search across the demo corpus; empty results if "
        "commentary is not loaded.",
        {"query": {"type": "string"}, "all_matches": {"type": "boolean"}},
        ["query"],
    ),
    tool_schema(
        "get_commentary",
        "Read broadcast commentary in an inclusive timeline bucket window. "
        "Returns start clocks, danger, outcome and sequence IDs for citations.",
        {"from_index": INT, "to_index": INT},
    ),
]


def citation_registry(b: dict) -> dict[str, str]:
    """Labels for real actions, markers and sequences, including substitutions."""
    registry = {}
    names = {
        p["player_id"]: p["short_name"]
        for side in b["match"]["lineups"].values()
        for p in side
    }
    for e in b["events"]:
        action = (
            ("penalty goal" if e["type"] == "shot_penalty" else "goal")
            if e["result"] == "goal"
            else e["type"].replace("_", " ")
        )
        registry["ev:" + e["id"]] = (
            f"{clock_label(e['period'], e['minute'])} "
            f"{e['player'] or b['match']['teams'][e['team']]['name']} {action}"
        )
    for m in b["match"]["markers"]:
        label = (
            f"{clock_label(m['period'], m['minute'])} {names.get(m['player_id'], '')} "
        )
        if m["type"] == "sub":
            label += f"on for {names.get(m['player_off_id'], '')}"
        elif m["type"] == "card":
            label += f"{m['detail'].replace('_', ' ')} card"
        else:
            label += "penalty goal" if m["detail"] == "penalty" else "goal"
        registry["ev:" + m["event_id"]] = label
    for s in b["sequences"]:
        registry["seq:" + s["id"]] = (
            f"{s['start']['label']} {b['match']['teams'][s['team']]['name']} sequence"
        )
    return registry


def citation_exists(kind: str, ref: str, b: dict) -> bool:
    """A cited ID is a real action, marker or possession sequence of the match.

    Sequences outside the top-danger list are valid: the UI rebuilds any
    sequence from its events.
    """
    if f"{kind}:{ref}" in citation_registry(b):
        return True
    return kind == "seq" and any(e["sequence_id"] == ref for e in b["events"])


def _dispatch(match_id: str, name: str, args: dict) -> dict:
    if name == "get_player_profile":
        from matchmind.players.service import analyst_profile

        return analyst_profile(int(args["player_id"]), match_id)
    b = bundle(match_id)
    events = pd.DataFrame(b["events"])
    if name == "get_window_stats":
        result = get_window_stats(
            pd.DataFrame(b["minutes"]),
            events,
            **{k: args[k] for k in ("from_minute", "to_minute", "period") if k in args},
        )
    elif name == "get_events":
        kinds = args.get("types", [])
        team = args.get("team")
        start = args.get("from_minute", 0)
        end = args.get("to_minute", 150)
        limit = max(1, min(int(args.get("limit", 30)), 60))
        selected = [
            e
            for e in b["events"]
            if (
                not kinds
                or any(
                    e["type"] == k
                    or (k == "shot" and e["type"].startswith("shot"))
                    or (k == "goal" and e["result"] == "goal")
                    for k in kinds
                )
            )
            and (not team or e["team"] == team)
            and start <= e["minute"] <= end
        ]
        markers = [
            m
            for m in b["match"]["markers"]
            if (not kinds or m["type"] in kinds)
            and (not team or m["team"] == team)
            and start <= m["minute"] <= end
        ]
        result = {
            "events": [
                {
                    k: e[k]
                    for k in (
                        "id",
                        "period",
                        "minute",
                        "second",
                        "team",
                        "player",
                        "type",
                        "result",
                        "xg",
                        "vaep",
                        "sequence_id",
                    )
                }
                for e in selected[:limit]
            ],
            "markers": markers[:limit],
            "n_events": len(selected),
            "n_markers": len(markers),
        }
    elif name == "get_top_sequences":
        rows = [
            r
            for r in b["sequences"]
            if not args.get("team") or r["team"] == args["team"]
        ]
        rows = rows[: max(1, min(int(args.get("limit", 3)), 10))]
        result = {"sequences": rows, "count": len(rows)}
    elif name == "get_player_rankings":
        rows = get_player_rankings(
            pd.DataFrame(b["players"]),
            events,
            sort=args.get("sort", "vaep"),
            team=args.get("team"),
            limit=max(1, min(int(args.get("limit", 8)), 15)),
        )
        result = {
            "players": rows,
            "ranking": args.get("sort", "vaep"),
            "count": len(rows),
        }
    elif name == "find_turning_points":
        result = {"turning_points": b["turning_points"]}
    elif name == "run_counterfactual":
        result = run_counterfactual(match_id, args["event_id"], args["change"])
    elif name == "shot_alternatives":
        from matchmind.api.shot_alternatives import shot_alternatives

        result = shot_alternatives(match_id, args["event_id"])
    elif name == "search_moments":
        result = search_moments(
            args["query"], None if args.get("all_matches") else match_id
        )
    elif name == "get_commentary":
        result = get_commentary(match_id, args.get("from_index"), args.get("to_index"))
    else:
        raise ValueError("Unknown analyst tool")
    registry = citation_registry(b)
    # IDs still appear in results; labels let the model quote display clocks correctly.
    from matchmind.analyst.grounding import references

    labels = {ref: registry[ref] for ref in references(result) if ref in registry}
    # Search may cite a different match; short shot/card sequences are absent
    # from the top-sequences endpoint but remain valid commentary evidence.
    for row in result.get("results", []) + result.get("lines", []):
        label = row.get("label") or row.get("start", {}).get("label", "")
        team_name = (
            row.get("match", {}).get(row["team"])
            or b["match"]["teams"][row["team"]]["name"]
        )
        labels["seq:" + row["sequence_id"]] = f"{label} {team_name} sequence"
    result["evidence_labels"] = labels
    result["match"] = {
        "teams": {s: b["match"]["teams"][s]["name"] for s in ("home", "away")},
        "score": b["match"]["score"],
        "season": b["match"]["season"],
    }
    result["metric_notes"] = {
        "possession": "Pass-share proxy",
        "xg": "Model xG when populated; sb_xg fallback",
        "vaep": "Model VAEP when populated; threat-gain proxy fallback",
    }
    result["display_numbers"] = display_evidence(result)
    return result


async def dispatch(match_id: str, name: str, args: dict) -> dict:
    """Move synchronous metrics, DB and embedding work off the event loop."""
    return await asyncio.to_thread(_dispatch, match_id, name, args)


def _minutes(args: dict) -> str:
    start, end = args.get("from_minute"), args.get("to_minute")
    if start is None and end is None:
        return "the whole match"
    start = 0 if start is None else start
    end = 120 if end is None else end
    return f"minutes {start} to {end}"


def summarize(name: str, args: dict, result: dict) -> str:
    """One plain-English line on what a tool found, computed in Python for the UI."""
    if "error" in result:
        return "That calculation wasn't available, so the analyst tried another way."
    if name == "find_turning_points":
        points = result.get("turning_points", [])
        if not points:
            return "No clear shift in control was found."
        first = points[0]
        return (
            f"Found {len(points)} moments where control shifted, the biggest "
            f"from {first['start']['label']} to {first['end']['label']}."
        )
    if name == "get_window_stats":
        return f"Compared both teams over {_minutes(args)}."
    if name == "get_events":
        return (
            f"Pulled {result.get('n_events', 0)} actions and "
            f"{result.get('n_markers', 0)} key moments from {_minutes(args)}."
        )
    if name == "get_top_sequences":
        return f"Ranked the {result.get('count', 0)} most dangerous attacks."
    if name == "get_player_rankings":
        what = {
            "vaep": "overall impact",
            "progression": "moving the ball forward",
            "defending": "defending",
            "creation": "creating chances",
        }.get(result.get("ranking", ""), "impact")
        players = result.get("players", [])
        top = players[0].get("name") if players else None
        tail = f": {top} came out on top." if top else "."
        return f"Ranked players by {what}{tail}"
    if name == "run_counterfactual":
        if result.get("negligible"):
            return "Ran the what-if model: it sees almost no difference."
        outcome = result.get("result")
        if outcome:
            side = max(
                ("home", "away"),
                key=lambda k: outcome["modelled"][k] - outcome["factual"][k],
            )
            team = result.get("match", {}).get("teams", {}).get(side, side)
            before = round(outcome["factual"][side] * 100)
            after = round(outcome["modelled"][side] * 100)
            return (
                f"Ran the what-if model: {team}'s chance of winning goes from "
                f"{before}% to {after}%."
            )
        return "Ran the what-if model with and without that moment."
    if name == "shot_alternatives":
        options = result.get("options", [])
        verdict = {
            "pass_higher": "a pass looked better than the shot",
            "shot_higher": "the shot was the better option",
            "similar": "shooting and passing were about equal",
        }.get(result.get("comparison", ""), "no passing option was found")
        return f"Checked {len(options)} passing options: {verdict}."
    if name == "search_moments":
        found = len(result.get("results", []))
        return f"Searched the commentary and found {found} matching moments."
    if name == "get_commentary":
        return f"Read {len(result.get('lines', []))} lines of match commentary."
    if name == "get_player_profile":
        who = result.get("short_name") or result.get("name") or "the player"
        return f"Loaded {who}'s profile and career numbers."
    return "Done."
