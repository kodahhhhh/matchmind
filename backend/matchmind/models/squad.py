"""Pure, strictly historical squad features. No HTTP or database access."""

from collections import Counter

import numpy as np
import pandas as pd

TEAM_FEATURES = [
    "xi_log_total",
    "xi_mean_log",
    "bench_log_total",
    "mean_age",
    "observed_caps",
    "missing_starters_log_value",
    "new_signings_share",
    "valuation_coverage",
]
SQUAD_FEATURES = [
    f"{feature}_{kind}" for feature in TEAM_FEATURES for kind in ("diff", "level")
]
LIVE_FEATURES = ["pitch_log_value_diff", "pitch_value_coverage"]


def historical_value(
    dates: np.ndarray, amounts: np.ndarray, cutoff: pd.Timestamp
) -> float:
    """Sorted dated snapshots: strictly before cutoff, never the current snapshot."""
    if pd.isna(cutoff):
        return np.nan
    pos = np.searchsorted(dates, cutoff.to_datetime64(), side="left") - 1
    return float(amounts[pos]) if pos >= 0 else np.nan


def value_before(history: pd.DataFrame, player_id: int, date: pd.Timestamp) -> float:
    """Same-day updates are excluded because publication times are unknown."""
    rows = history[history.player_id == player_id].sort_values("date")
    return historical_value(
        rows.date.to_numpy(), rows.market_value_in_eur.to_numpy(), date
    )


def team_features(
    xi: list[int],
    bench: list[int],
    date: pd.Timestamp,
    values: dict[int, float],
    births: dict[int, pd.Timestamp],
    previous_xis: list[list[int]],
    caps: dict[int, int],
    new_signings: dict[int, bool],
) -> dict[str, float]:
    """All historical arguments must already be restricted to dates < kick-off."""
    known = [values[p] for p in xi if np.isfinite(values.get(p, np.nan))]
    reserves = [values[p] for p in bench if np.isfinite(values.get(p, np.nan))]
    ages = [
        (date - births[p]).days / 365.25
        for p in xi
        if p in births and pd.notna(births[p])
    ]
    usual = Counter(p for lineup in previous_xis[-5:] for p in lineup)
    absent = [p for p, n in usual.items() if n >= 3 and p not in xi]
    missing = [values[p] for p in absent if np.isfinite(values.get(p, np.nan))]
    return {
        "xi_log_total": float(np.log1p(sum(known))) if known else np.nan,
        "xi_mean_log": float(np.mean(np.log1p(known))) if known else np.nan,
        "bench_log_total": float(np.log1p(sum(reserves))) if reserves else np.nan,
        "mean_age": float(np.mean(ages)) if ages else np.nan,
        "observed_caps": float(np.mean([caps.get(p, 0) for p in xi])) if xi else np.nan,
        "missing_starters_log_value": float(np.log1p(sum(missing)))
        if len(previous_xis) >= 3
        else np.nan,
        "new_signings_share": float(
            np.mean([new_signings[p] for p in xi if p in new_signings])
        )
        if any(p in new_signings for p in xi)
        else np.nan,
        "valuation_coverage": len(known) / 11,
    }


def contrasts(home: dict[str, float], away: dict[str, float]) -> dict[str, float]:
    return {
        f"{feature}_{kind}": home[feature] - away[feature]
        if kind == "diff"
        else (home[feature] + away[feature]) / 2
        for feature in TEAM_FEATURES
        for kind in ("diff", "level")
    }


def live_strength(
    events: list[dict], player_values: dict[int, float], boundaries: pd.DataFrame
) -> pd.DataFrame:
    """Track actual players strictly before each boundary, including half-time subs."""
    starters = [e for e in events if e["type"]["name"] == "Starting XI"]
    if len(starters) != 2:
        raise ValueError("Expected two announced starting XIs")
    sides = {
        e["team"]["id"]: {p["player"]["id"] for p in e["tactics"]["lineup"]}
        for e in starters
    }
    team_ids = list(sides)
    changes = sorted(
        [e for e in events if e["type"]["name"] != "Starting XI" and e["period"] <= 2],
        key=lambda e: (e["period"], e["minute"], e["second"], e["index"]),
    )
    cursor, rows = 0, []
    for row in boundaries.sort_values(["period", "minute"]).itertuples():
        while cursor < len(changes):
            event = changes[cursor]
            if (event["period"], event["minute"] * 60 + event["second"]) >= (
                row.period,
                row.minute * 60,
            ):
                break
            active = sides.get(event["team"]["id"])
            if active is not None:
                player = event.get("player", {}).get("id")
                if event["type"]["name"] == "Substitution":
                    active.discard(player)
                    active.add(event["substitution"]["replacement"]["id"])
                card = (
                    event.get("foul_committed", {})
                    .get("card", event.get("bad_behaviour", {}).get("card", {}))
                    .get("name")
                )
                if card in ("Red Card", "Second Yellow"):
                    active.discard(player)
            cursor += 1
        values = [
            [
                player_values[p]
                for p in sides[tid]
                if np.isfinite(player_values.get(p, np.nan))
            ]
            for tid in team_ids
        ]
        complete = all(
            len(v) >= max(1, len(sides[t]) * 0.8)
            for v, t in zip(values, team_ids, strict=True)
        )
        rows.append(
            {
                "period": row.period,
                "minute": row.minute,
                "pitch_log_value_diff": float(
                    np.log1p(sum(values[0])) - np.log1p(sum(values[1]))
                )
                if complete
                else np.nan,
                "pitch_value_coverage": min(
                    len(v) / max(1, len(sides[t]))
                    for v, t in zip(values, team_ids, strict=True)
                ),
            }
        )
    return pd.DataFrame(rows)
