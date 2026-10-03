"""Sol's fixed tool schemas and orchestration over pure metrics functions."""

import asyncio

import pandas as pd

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
        "Modelled hypothetical from empirical analog quantiles; not causal certainty.",
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
        "search_moments",
        "Hybrid commentary search across the demo corpus; empty results if "
        "commentary is not loaded.",
        {"query": {"type": "string"}, "all_matches": {"type": "boolean"}},
        ["query"],
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


def _dispatch(match_id: str, name: str, args: dict) -> dict:
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
    elif name == "search_moments":
        result = search_moments(
            args["query"], None if args.get("all_matches") else match_id
        )
    else:
        raise ValueError("Unknown analyst tool")
    registry = citation_registry(b)
    # IDs still appear in results; labels let the model quote display clocks correctly.
    from matchmind.analyst.grounding import references

    labels = {ref: registry[ref] for ref in references(result) if ref in registry}
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
