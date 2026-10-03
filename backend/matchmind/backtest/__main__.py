"""Run `uv run --group models python -m matchmind.backtest fetch|train|run|all`."""

import argparse
import json
from datetime import UTC, datetime

from matchmind.backtest.common import output, save


def run() -> None:
    from matchmind.backtest import polymarket, prematch
    from matchmind.backtest.contracts import Backtest

    bookmaker, _ = prematch.run()
    market, diagnostic = polymarket.run()
    kalshi = json.loads((output() / "kalshi_coverage.json").read_text())
    histories = json.loads((output() / "polymarket_histories.json").read_text())
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": [
            {
                "name": "Pinnacle / football-data.co.uk",
                "matches": 306,
                "notes": (
                    "All 306 Bundesliga 2015/16 matches joined; 153 evaluation "
                    "matches, matchweeks 18–34. Also fetched 2023/24: all 34 "
                    "catalogue Leverkusen matches joined; incomplete league "
                    "excluded from betting evaluation."
                ),
            },
            {
                "name": "Polymarket",
                "matches": len({i["match"]["match_id"] for i in histories}),
                "notes": (
                    f"{len(histories)} regulation-market events with verified "
                    f"scheduled clocks; {diagnostic['aligned_matches']} matches "
                    "pass both-half goal-jump alignment. Other discovered "
                    "markets have exclusions in the resolution audit."
                ),
            },
            {"name": "Kalshi", "matches": 0, "notes": kalshi["notes"]},
        ],
        "strategies": bookmaker + market,
        "caveats": [
            (
                "Historical research, not a claim of achievable trading "
                "returns. No live bets were placed."
            ),
            (
                "Existing shuffled OOF xG/VAEP include future seasons. W10 "
                "regenerates features with separate pre-August-2015 models; "
                "original app artifacts remain untouched."
            ),
            (
                "Pre-match: no bets in weeks 1–5; tune only weeks 6–17; "
                "evaluate weeks 18–34. Ratings update only after a complete "
                "previous round."
            ),
            (
                "Opening-odds rows are payout sensitivity only, NOT tradable "
                "profit evidence: closing odds choose the bets and opening "
                "quote timestamps are unavailable. Closing-price CLV is "
                "mechanically zero."
            ),
            (
                "2023/24 is only Leverkusen coverage, not a full league; no "
                "league backtest is reported for it."
            ),
            (
                "In-play result model excludes every World Cup 2022, Euro "
                "2024 and Copa América 2024 match. Base feature models, "
                "result training, calibration and validation are disjoint "
                "chronological partitions."
            ),
            (
                "The World Cup final market includes extra time and "
                "penalties. A regulation model cannot value it, so it is "
                "excluded."
            ),
            (
                "Minute-level trade histories are not order books or "
                "guaranteed executable asks. Both YES and NO histories are "
                "fetched; no synthetic NO fill. No historical trading fees "
                "assumed for these markets; +1¢ and +2¢ cost sensitivities "
                "are shown."
            ),
            (
                "Clock alignment is retrospective data QA, using goal-"
                "direction jumps only, never profits. Both halves must be "
                "verified; goal-free or uncertain matches are excluded. No "
                "entries during the three match-clock minutes after an observed "
                "goal; future goals never suppress an entry."
            ),
            (
                "Backward as-of prices must be less than 90 seconds old; no "
                "forward interpolation. Model inputs strictly precede the "
                "match-clock minute, with an additional three-minute information "
                "lag; no new entries after minute 85."
            ),
            (
                "Polymarket sample is small and selected by "
                "market/data/alignment availability. Match-cluster bootstrap "
                "95% intervals are descriptive, not proof of future edge; "
                "they do not correct selection bias or execution uncertainty."
            ),
            (
                "Brier is the sum of squared errors across three outcomes "
                "(0–2). Polymarket three-way prices are normalized only for "
                "probability scoring; execution uses each actual binary "
                "price."
            ),
            (
                "Bankroll curves and drawdown use settled round totals "
                "(Pinnacle) or settled daily totals (Polymarket), not mark-"
                "to-market or intraday drawdown. Kelly ROI intervals resample"
                " realized match stakes without re-optimizing a hypothetical "
                "path."
            ),
        ],
    }
    Backtest.model_validate(result)
    save(output() / "backtest.json", result)
    print(
        json.dumps(
            [
                {
                    k: s[k]
                    for k in [
                        "id",
                        "n_matches",
                        "n_bets",
                        "staked",
                        "pnl",
                        "roi",
                        "roi_ci95",
                        "hit_rate",
                        "max_drawdown",
                        "brier_model",
                        "brier_market",
                    ]
                }
                for s in result["strategies"]
            ],
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fetch", "train", "run", "all"])
    args = parser.parse_args()
    if args.command in ("fetch", "all"):
        from matchmind.backtest import fetch, markets

        fetch.fetch()
        markets.fetch()
    if args.command in ("train", "all"):
        from matchmind.backtest import inplay, prematch

        prematch.train()
        inplay.train()
    if args.command in ("run", "all"):
        run()


if __name__ == "__main__":
    main()
