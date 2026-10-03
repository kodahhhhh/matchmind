"""Fixed-rule, delayed-information YES/NO paper execution with match bootstrap."""

import json

import numpy as np
import pandas as pd

from matchmind.backtest.common import output, save
from matchmind.backtest.markets import align, last_price
from matchmind.backtest.statistics import OUTCOMES, scores, summary

# Preregistered constants, never tuned on tournament outcomes or profits.
EDGE = 0.10
STAKE = 100.0
EMBARGO_SECONDS = 180
INFORMATION_LAG_MINUTES = 3


def entry_allowed(period: int, minute: int, goals: list[dict]) -> bool:
    """Only already-observed goals can embargo an entry; future goals cannot."""
    recent_goal = any(
        g["period"] == period and 0 < minute * 60 - g["seconds"] <= EMBARGO_SECONDS
        for g in goals
    )
    return 1 <= minute <= 85 and not recent_goal


def run() -> tuple[list[dict], dict]:
    from matchmind.api.repository import bundle

    discovered = json.loads((output() / "polymarket_discovery.json").read_text())
    # Excluded contract types still expose market availability, with no false curve.
    for item in sorted(discovered, key=lambda d: float(d["event"].get("volume", 0))):
        mid, event = item["match"]["match_id"], item["event"]
        save(
            output() / f"market_{mid.replace(':', '_')}.json",
            {
                "match_id": mid,
                "source": "polymarket",
                "market_url": f"https://polymarket.com/event/{event['slug']}",
                "volume": float(event.get("volume", 0)),
                "aligned": False,
                "offset_seconds": None,
                "series": [],
                "bets": [],
            },
        )
    histories = json.loads((output() / "polymarket_histories.json").read_text())
    predictions = pd.read_parquet(output() / "inplay_predictions.parquet")
    audits, accepted = [], []
    for item in histories:
        audit = align(item)
        mid = item["match"]["match_id"]
        actual = predictions[predictions.match_id == mid]
        if actual.empty:
            audit.update(
                aligned=False, reason="No excluded-tournament model predictions"
            )
        elif any(
            m["resolved"] != float(OUTCOMES[int(actual.iloc[0]["result"])] == side)
            for side, m in item["markets"].items()
        ):
            audit.update(
                aligned=False, reason="Resolution disagrees with regulation result"
            )
        audits.append(audit)
        if audit["aligned"]:
            accepted.append((item, audit))
    save(output() / "polymarket_alignment.json", audits)
    # Keep unaligned matches visible as evidence, without inventing plot values.
    for item, audit in zip(histories, audits, strict=True):
        mid = item["match"]["match_id"]
        save(
            output() / f"market_{mid.replace(':', '_')}.json",
            {
                "match_id": mid,
                "source": "polymarket",
                "market_url": item["market_url"],
                "volume": item["volume"],
                "aligned": audit["aligned"],
                "offset_seconds": audit.get("offset_seconds"),
                "series": [],
                "bets": [],
            },
        )
    strategies, diagnostic = (
        [],
        {
            "threshold": EDGE,
            "stake": STAKE,
            "embargo_seconds": EMBARGO_SECONDS,
            "information_lag_minutes": INFORMATION_LAG_MINUTES,
            "aligned_matches": len(accepted),
            "calibration": {},
            "per_match_pnl": {},
        },
    )
    calibration = {m: [] for m in (15, 30, 45, 60, 75)}
    timeline = {}
    for item, _ in accepted:
        mid = item["match"]["match_id"]
        timeline[mid] = {(r["period"], r["minute"]): r for r in bundle(mid)["minutes"]}
    # Settlement equity groups overlapping matches by UTC date; no interim fictitious
    # gains.
    for slippage in (0.0, 0.01, 0.02):
        bets, per_match = [], []
        for item, audit in sorted(accepted, key=lambda x: x[0]["kickoff"]):
            mid = item["match"]["match_id"]
            rows = predictions[predictions.match_id == mid].sort_values(
                ["period", "minute"]
            )
            feature_rows = {
                (r["period"], r["minute"]): r for r in rows.to_dict("records")
            }
            positions, series = set(), []
            label = f"{item['match']['home']['name']} – {item['match']['away']['name']}"
            for row in rows.to_dict("records"):
                period, minute = row["period"], row["minute"]
                timestamp = (
                    item["kickoff"] + minute * 60 + audit["period_offsets"][str(period)]
                )
                prices = {
                    side: last_price(m["prices"]["YES"], timestamp)
                    for side, m in item["markets"].items()
                }
                delayed = feature_rows.get((period, minute - INFORMATION_LAG_MINUTES))
                if delayed is None:
                    continue
                probs = {s: float(delayed[f"p_{s}"]) for s in OUTCOMES}
                if all(s in prices and prices[s] is not None for s in OUTCOMES):
                    key = (period, minute)
                    if key in timeline[mid]:
                        t = timeline[mid][key]
                        series.append(
                            {
                                "index": t["index"],
                                "label": t["label"],
                                "minute": minute,
                                "period": period,
                                "market": prices,
                                "model": probs,
                            }
                        )
                    if (
                        slippage == 0
                        and minute in calibration
                        and (minute != 45 or period == 1)
                    ):
                        calibration[minute].append(
                            {
                                "match_id": mid,
                                "result": row["result"],
                                "model": [probs[s] for s in OUTCOMES],
                                "market": [prices[s] for s in OUTCOMES],
                            }
                        )
                if not entry_allowed(period, minute, audit["goals"]):
                    continue
                for side, m in item["markets"].items():
                    if side in positions:
                        continue
                    choices = []
                    for binary in ("YES", "NO"):
                        price = last_price(m["prices"][binary], timestamp)
                        probability = (
                            probs[side] if binary == "YES" else 1 - probs[side]
                        )
                        if price is None or not 0.02 <= price <= 0.98:
                            continue
                        paid = price + slippage
                        if paid >= 1 or probability - price <= EDGE:
                            continue
                        choices.append(
                            (probability - price, binary, paid, probability, price)
                        )
                    if not choices:
                        continue
                    _, binary, paid, probability, quoted = max(choices)
                    won = m["resolved"] if binary == "YES" else 1 - m["resolved"]
                    bet = {
                        "match_id": mid,
                        "label": label,
                        "outcome": side,
                        "side": binary,
                        "price_or_odds": paid,
                        "model_prob": probability,
                        "market_prob": quoted,
                        "stake": STAKE,
                        "pnl": STAKE * (won / paid - 1),
                        "minute": minute,
                    }
                    bets.append(bet)
                    positions.add(side)
            match_bets = [b for b in bets if b["match_id"] == mid]
            per_match.append(
                {
                    "match_id": mid,
                    "label": label,
                    "n_bets": len(match_bets),
                    "pnl": sum(b["pnl"] for b in match_bets),
                    "date": pd.Timestamp(item["kickoff"], unit="s", tz="UTC")
                    .date()
                    .isoformat(),
                }
            )
            if slippage == 0:
                save(
                    output() / f"market_{mid.replace(':', '_')}.json",
                    {
                        "match_id": mid,
                        "source": "polymarket",
                        "market_url": item["market_url"],
                        "volume": item["volume"],
                        "aligned": True,
                        "offset_seconds": audit["offset_seconds"],
                        "series": series,
                        "bets": match_bets,
                    },
                )
        bankroll = 10000.0
        equity = [{"i": 0, "label": "Start", "bankroll": bankroll}]
        for date in sorted({r["date"] for r in per_match}):
            bankroll += sum(r["pnl"] for r in per_match if r["date"] == date)
            equity.append({"i": len(equity), "label": date, "bankroll": bankroll})
        diagnostic["per_match_pnl"][str(slippage)] = per_match
        data = summary(bets, [i["match"]["match_id"] for i, _ in accepted], equity)
        samples = [s for values in calibration.values() for s in values]
        model_brier, market_brier = None, None
        if samples:
            y = np.array([s["result"] for s in samples])
            model_brier = scores(y, np.array([s["model"] for s in samples]))["brier"]
            market_brier = scores(y, np.array([s["market"] for s in samples]))["brier"]
        strategies.append(
            {
                "id": f"polymarket-{round(slippage * 100)}c",
                "name": f"Polymarket · {round(slippage * 100)}¢ slippage",
                "market": "polymarket",
                "description": (
                    "Regulation YES/NO; three-minute information lag; "
                    "fixed 10 percentage-point probability "
                    "edge; $100 stake; one position per market; minute <86; hold "
                    "to resolution. Historical prices are not executable quotes."
                ),
                "eval_period": (
                    "Euro / Copa América 2024 and World Cup 2022 eligible "
                    "regulation markets"
                ),
                **data,
                "brier_model": model_brier,
                "brier_market": market_brier,
            }
        )
    for minute, samples in calibration.items():
        diagnostic["calibration"][str(minute)] = {"n_matches": len(samples)}
        if samples:
            y = np.array([s["result"] for s in samples])
            diagnostic["calibration"][str(minute)].update(
                model=scores(y, np.array([s["model"] for s in samples])),
                market=scores(y, np.array([s["market"] for s in samples])),
            )
    save(output() / "polymarket_diagnostics.json", diagnostic)
    return strategies, diagnostic
