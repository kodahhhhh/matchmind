"""Period-aware change points in rolling momentum."""

import numpy as np
import pandas as pd
import ruptures as rpt


def window_stats(frame: pd.DataFrame) -> dict:
    """Summarise timeline buckets; possession and tilt remain fractions."""
    rows = frame.to_dict("records")
    out = {}
    for side in ("home", "away"):
        out[side] = {
            "possession": round(np.mean([r[side]["possession"] for r in rows]), 3)
            if rows
            else 0.5,
            "field_tilt": round(np.mean([r[side]["field_tilt"] for r in rows]), 3)
            if rows
            else 0.5,
            "xg": round(sum(r[side]["xg"] for r in rows), 3),
            "shots": sum(r[side]["shots"] for r in rows),
        }
    out["momentum"] = round(float(frame["momentum"].mean()), 4) if rows else 0.0
    return out


def find_turning_points(
    timeline: pd.DataFrame, events: pd.DataFrame, markers: list[dict], match_id: str
) -> list[dict]:
    """Binseg candidates, refined locally by eight-minute mean shifts.

    Standardise within each period; use up to three breakpoints per period.
    Refine +/- three buckets against local before/after momentum differences.
    Never straddle a half-time interval; suppress overlapping eight-minute windows.
    """
    if timeline.empty:
        return []
    candidates = []
    for _, part in timeline.groupby("period", sort=True):
        part = part.reset_index(drop=True)
        n = len(part)
        if n < 16:
            continue
        values = part["momentum"].to_numpy(dtype=float)
        scale = float(np.std(values))
        if scale < 1e-8:
            continue
        breaks = (
            rpt.Binseg(model="l2", min_size=5, jump=1)
            .fit((values / scale).reshape(-1, 1))
            .predict(n_bkps=min(3, n // 8 - 1))[:-1]
        )
        for b in breaks:
            best = None
            for i in range(max(5, b - 3), min(n - 4, b + 4)):
                before = part.iloc[max(0, i - 8) : i]
                after = part.iloc[i : min(n, i + 8)]
                delta = float(after["momentum"].mean() - before["momentum"].mean())
                if best is None or abs(delta) > best[0]:
                    best = (
                        abs(delta),
                        int(part.iloc[i]["index"]),
                        delta,
                        before,
                        after,
                    )
            if best:
                candidates.append(best)
    chosen = []
    for candidate in sorted(candidates, key=lambda x: -x[0]):
        if all(abs(candidate[1] - c[1]) >= 10 for c in chosen):
            chosen.append(candidate)
        if len(chosen) == 3:
            break
    out = []
    for rank, (magnitude, _, delta, before, after) in enumerate(chosen, 1):
        lo, hi = after.iloc[0], after.iloc[-1]
        key = [
            m["event_id"]
            for m in markers
            if m["type"] == "goal"
            and m["period"] == int(lo["period"])
            and int(lo["minute"]) <= m["minute"] <= int(hi["minute"])
        ]
        if not events.empty:
            shots = (
                events[
                    (events["period"] == lo["period"])
                    & events["minute"].between(lo["minute"], hi["minute"])
                    & events["type"].str.startswith("shot")
                ]
                .sort_values("xg", ascending=False)
                .head(3)
            )
            key.extend(eid for eid in shots["id"] if eid not in key)

        def ref(row: pd.Series) -> dict:
            return {
                "index": int(row["index"]),
                "period": int(row["period"]),
                "minute": int(row["minute"]),
                "label": row["label"],
            }

        out.append(
            {
                "id": f"{match_id}:tp{rank}",
                "rank": rank,
                "start": ref(lo),
                "end": ref(hi),
                "team_gaining": "home" if delta > 0 else "away",
                "magnitude": round(magnitude, 4),
                "before": window_stats(before),
                "after": window_stats(after),
                "key_event_ids": key,
            }
        )
    return out
