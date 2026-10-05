"""Prefer full streams and enrich overlapping lite matches with provenance."""

import json
from pathlib import Path

from matchpulse.sources.common import canonical_team, normal_name, save_json


def match_key(match: dict) -> tuple | None:
    """Exact dated team identity, using the project's reviewed club aliases."""
    if not match.get("match_date"):
        return None
    return (
        match["match_date"],
        match.get("gender", "male"),
        *sorted(
            normal_name(canonical_team(match[s]["name"])) for s in ("home", "away")
        ),
    )


def scores(match: dict) -> dict:
    """Compare scores by canonical team, independent of home/away ordering."""
    return {
        normal_name(canonical_team(match[s]["name"])): match[f"{s}_score"]
        for s in ("home", "away")
    }


def priority(match: dict) -> tuple:
    """StatsBomb precedes other full data, then rich FotMob, then Understat."""
    source = match["match_id"].split(":")[0]
    return (
        0
        if source == "sb"
        else 1
        if match.get("data_tier") == "full"
        else 2
        if source == "fm"
        else 3,
        match["match_id"],
    )


def select(matches: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    """Keep conflicting/ambiguous evidence visible rather than guessing a merge."""
    selected, seen, aliases = {}, {}, []
    for match in sorted(matches, key=priority):
        key = match_key(match)
        previous = seen.get(key) if key else None
        if previous and scores(match) == scores(previous):
            aliases.append(
                {
                    "match_id": match["match_id"],
                    "preferred": previous["match_id"],
                    "reason": "duplicate",
                }
            )
        else:
            selected[match["match_id"]] = match
            if previous:
                aliases.append(
                    {
                        "match_id": match["match_id"],
                        "preferred": previous["match_id"],
                        "reason": "score_conflict_kept",
                    }
                )
            elif key:
                seen[key] = match
    return selected, aliases


def canonical_matches(matches: list[dict]) -> dict[str, dict]:
    """Serve one loaded match per exact score-consistent dated team pair."""
    return select(matches)[0]


def reconcile(data_dir: Path, database_url: str | None = None) -> dict:
    """Merge Understat aggregates into rich FotMob; export preferred catalogue."""
    reference = json.loads((data_dir / "catalogue/matches.json").read_text())
    source_matches = []
    for path in (data_dir / "sources").glob("catalogue_*.json"):
        if path.stem == "catalogue_canonical":
            continue
        source_matches.extend(json.loads(path.read_text()))
    selected, aliases = select(reference + source_matches)
    by_id = {m["match_id"]: m for m in source_matches}
    merged = 0
    for alias in aliases:
        if alias["reason"] != "duplicate":
            continue
        other, preferred = alias["match_id"], alias["preferred"]
        if not other.startswith("us:") or not preferred.startswith("fm:"):
            continue
        path = data_dir / f"sources/fotmob/lite/{preferred.split(':')[1]}.json"
        raw = data_dir / f"sources/understat/lite/{other.split(':')[1]}.json"
        if not path.exists() or not raw.exists():
            continue
        payload, understat = json.loads(path.read_text()), json.loads(raw.read_text())
        # Preserve distinct provider values and source IDs; never turn their xG
        # or ratings into our model's outputs. FotMob has the richer shot clock.
        mapping = {
            s: next(
                t
                for t in ("home", "away")
                if normal_name(canonical_team(by_id[preferred][s]["name"]))
                == normal_name(canonical_team(by_id[other][t]["name"]))
            )
            for s in ("home", "away")
        }
        payload["provider_team_stats"] = {
            "fotmob": payload.get("team_stats"),
            "understat": {
                s: understat.get("provider_team_stats", {}).get(t)
                for s, t in mapping.items()
            },
        }
        for side, other_side in mapping.items():
            roster = understat.get("lineups", {}).get(other_side, [])
            if not payload.get("lineups", {}).get(side):
                payload.setdefault("lineups", {})[side] = roster
            else:
                by_name = {}
                for player in roster:
                    by_name.setdefault(normal_name(player["name"]), []).append(player)
                for player in payload["lineups"][side]:
                    same = by_name.get(normal_name(player["name"]), [])
                    if len(same) == 1:
                        player.setdefault("minutes", same[0].get("minutes"))
                        if player.get("position") is None:
                            player["position"] = same[0].get("position")
        if not payload["shots"] and understat.get("shots"):
            payload["shots"] = [
                {
                    **shot,
                    "id": f"{preferred}:{index}",
                    "team": next(s for s, t in mapping.items() if t == shot["team"]),
                    "original_source_event_id": shot["id"],
                    "source_provider": "understat",
                }
                for index, shot in enumerate(understat["shots"])
            ]
            payload["xg_provenance"] = (
                understat["xg_provenance"] + "; Understat shot fallback"
            )
        payload["capabilities"].update(
            shots=bool(payload["shots"]),
            lineups=any(payload.get("lineups", {}).values()),
            own_xg=any(s["xg"] is not None for s in payload["shots"]),
        )
        payload["alternate_sources"] = [{"match_id": other, "path": str(raw)}]
        payload["capabilities"]["provider_team_stats"] = True
        payload["meta"]["capabilities"] = payload["capabilities"]
        save_json(path, payload)
        if database_url:
            from matchpulse.db.load_sources import load_lite

            load_lite(database_url, path)
        merged += 1
    # Canonical export contains only new sources; the orchestrator can merge it
    # with StatsBomb without adding superseded lite entries from per-source files.
    canonical = [m for mid, m in selected.items() if not mid.startswith("sb:")]
    save_json(data_dir / "sources/catalogue_canonical.json", canonical)
    report = {
        "source_matches": len(source_matches),
        "canonical_sources": len(canonical),
        "merged_fotmob_understat": merged,
        "aliases": aliases,
    }
    save_json(data_dir / "sources/reconciliation_report.json", report)
    return report


def main() -> None:
    """Refresh alias/enrichment exports, optionally updating staging payloads."""
    import argparse

    from matchpulse.config import get_settings
    from matchpulse.db.load_sources import staging_url

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    url = staging_url(settings.database_url) if args.load else None
    report = reconcile(settings.data_dir, url)
    print(json.dumps({k: v for k, v in report.items() if k != "aliases"}, indent=2))


if __name__ == "__main__":
    main()
