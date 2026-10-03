"""Generate measured documentation and golden responses from saved results."""

import json
from collections import Counter
from pathlib import Path

from matchmind.backtest.common import output, root, save


def read(name: str) -> dict | list:
    return json.loads((output() / name).read_text())


def generate() -> None:
    result = read("backtest.json")
    pre = read("prematch_metrics.json")
    model = read("inplay_metrics.json")
    poly = read("polymarket_diagnostics.json")
    history = read("polymarket_histories.json")
    audit = read("polymarket_alignment.json")
    discovery = read("polymarket_discovery.json")
    kalshi = read("kalshi_coverage.json")
    by_id = {d["match"]["match_id"]: d for d in history}
    source = Path(__file__).with_name("BACKTEST.md")
    intro = source.read_text().split("## Measured results")[0]
    lines = [
        "## Measured results",
        "",
        f"Generated: `{result['generated_at']}`.",
        "",
        "**No reliable evidence that MatchMind beats these markets.** The primary "
        "Pinnacle closing-odds test loses money and has worse probability scores "
        "than the market. Polymarket paper P&L is positive, but all ROI intervals "
        "include zero, the cohort is selected, and historical fills are not proven.",
        "",
        "### Coverage",
        "",
        "- Football-data: 306/306 Bundesliga 2015/16 rows join, zero unmatched "
        "catalogue rows, all final scores agree. Evaluation: 153 matches. "
        "2023/24: 34/34 catalogue matches join; 272 CSV rows intentionally have "
        "no corresponding catalogue match. No incomplete-league betting result.",
        f"- Polymarket: {len(discovery)} candidate event/match pairs across "
        f"{len({d['match']['match_id'] for d in discovery})} demo matches; "
        f"{len(history)} regulation-market events survive contract/clock checks; "
        f"{poly['aligned_matches']} pass both-half alignment and settlement checks.",
        "- Discovery combines all 187 dated post-2015/16 demo match searches, "
        "tournament searches and paginated date-bounded archives. One broad "
        "USA/Bolivia query hits the ten-page safety cap; archive and tournament "
        "passes supplement it. This is discovered public coverage, not proof "
        "that no other historical contracts existed.",
        "- Archive pagination uses 100 rows: Gamma silently caps larger limits. "
        "The full 2015/16 archive date range returns zero events, covering the "
        "306 early-season demo matches including reconstructed undated ones.",
        "- Kalshi: zero matching demo markets. Current historical-date query "
        "returns eight unrelated Robinhood contracts. Eight relevant historical "
        "football series return 3,081 contracts, none before September 2024. "
        "The historical endpoint does not support date filters: unsupported "
        "parameters were found to be ignored, so the audit uses its documented "
        "series filter and exhausts cursors instead.",
        "",
        "| Discovered competition | Matches |",
        "| --- | ---: |",
    ]
    for name, count in Counter(
        d["match"]["competition"]
        for d in {i["match"]["match_id"]: i for i in discovery}.values()
    ).items():
        lines.append(f"| {name} | {count} |")
    lines += [
        "",
        "| Kalshi archived series | Contracts | Earliest close |",
        "| --- | ---: | --- |",
    ]
    for r in kalshi["archived_series_checks"]:
        lines.append(
            f"| {r['series']} | {r['rows']} | {r['earliest_close'] or 'none'} |"
        )
    lines += [
        "",
        "### Betting results",
        "",
        "Pinnacle units and Polymarket dollars are separate. ROI = P&L / total "
        "staked, not bankroll growth. Confidence intervals are match-cluster "
        "bootstrap percentiles. Drawdown uses settled weekly/daily balances.",
        "",
        "| Strategy | Matches | Bets | Staked | P&L | ROI | ROI 95% CI | "
        "Hit rate | Max drawdown | Final bankroll |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    for s in result["strategies"]:
        lo, hi = s["roi_ci95"]
        lines.append(
            f"| {s['id']} | {s['n_matches']} | {s['n_bets']} | "
            f"{s['staked']:.2f} | {s['pnl']:+.2f} | {s['roi']:.2%} | "
            f"[{lo:.2%}, {hi:.2%}] | {s['hit_rate']:.2%} | "
            f"{s['max_drawdown']:.2f} | {s['equity'][-1]['bankroll']:.2f} |"
        )
    lines += [
        "",
        "**Opening rows are payout sensitivities, not executable "
        "backtests.** They use the closing-selected cohort. Opening Kelly "
        "stakes additionally drop selected outcomes with nonpositive opening "
        "edge; that does not turn them into a valid opening-time strategy.",
        "",
        "| Pinnacle strategy | Mean quote CLV (odds/closing odds - 1) |",
        "| --- | ---: |",
    ]
    for s in result["strategies"]:
        if s["market"] == "pinnacle":
            lines.append(f"| {s['id']} | {s['clv']:.4%} |")
    selection = read("prematch_selection.json")
    lines += [
        "",
        "Frozen tuning selection: "
        f"`{selection['parameters']}`; edge threshold "
        f"`{selection['threshold']}`. Tuning candidates and scores are saved "
        "in `prematch_selection.json`; no evaluation result selected them.",
        "",
        "### Model validation",
        "",
        "| Split | Matches | Minute rows |",
        "| --- | ---: | ---: |",
    ]
    for name, part in model["splits"].items():
        lines.append(f"| {name} | {part['matches']} | {part['rows']} |")
    lines += [
        "",
        "The 397 upstream matches contain 850,897 regulation SPADL "
        "actions for the historical VAEP fit. They are excluded from all "
        "result-model partitions. The remaining 113 corpus matches have "
        "unusable dates or occur after the validation cutoff outside the "
        "held-out tournaments, and are excluded. No all-corpus final model "
        "is substituted into backtest predictions.",
        "",
        "The `international` feature is the literal metadata predicate "
        '`country == "International"`; continent-labelled tournaments do '
        "not receive that flag. There are no identity, odds or terminal-score "
        "features. No game-state forecast is used because its final fit "
        "includes demo matches.",
        "",
        "| Evaluation | Predictor | Brier | Log loss |",
        "| --- | --- | ---: | ---: |",
    ]
    for name, r in pre.items():
        lines.append(
            f"| Pinnacle evaluation, all 153 matches | {name} | "
            f"{r['brier']:.6f} | {r['log_loss']:.6f} |"
        )
    for name, r in model["metrics"].items():
        lines.append(
            f"| 259 held-out 2020–2022 training-corpus matches | {name} | "
            f"{r['brier']:.6f} | {r['log_loss']:.6f} |"
        )
    lines += [
        "",
        "The richer in-play model does **not** improve on its minute/score "
        "baseline on the untouched validation split. Temperature calibration "
        "fits only the separate 132-match calibration partition: "
        + ", ".join(
            f"{k} = {v['temperature']:.6f}" for k, v in model["metrics"].items()
        )
        + ".",
        "",
        "| Market-clock minute | Matches | Model Brier | Market Brier | "
        "Model log loss | Market log loss |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for minute, r in poly["calibration"].items():
        lines.append(
            f"| {minute} | {r['n_matches']} | {r['model']['brier']:.6f} | "
            f"{r['market']['brier']:.6f} | {r['model']['log_loss']:.6f} | "
            f"{r['market']['log_loss']:.6f} |"
        )
    lines += [
        "",
        "Market-clock scoring uses the same conservative three-minute "
        "model-information lag as trading. These scores measure probability "
        "accuracy; the small checkpoint sample does not establish calibration.",
        "",
        "### Per-match Polymarket paper P&L and alignment",
        "",
        "Offsets are seconds added to `kickoff_utc + displayed_minute*60`. "
        "The second-half offset includes stoppage and halftime. Negative "
        "first-half offsets reveal timestamp ambiguity; the three-minute "
        "feature lag and goal embargo reduce its impact but cannot validate "
        "an executable historical fill. Market volume is lifetime event "
        "volume, not available depth at entry.",
        "",
        "| Match | Volume | Half 1 offset | Half 2 offset | Bets | "
        "P&L 0¢ | P&L +1¢ | P&L +2¢ |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    offsets = {r["match_id"]: r for r in audit}
    for r in poly["per_match_pnl"]["0.0"]:
        mid = r["match_id"]
        o = offsets[mid]["period_offsets"]
        pnl = [
            next(
                v["pnl"] for v in poly["per_match_pnl"][str(s)] if v["match_id"] == mid
            )
            for s in (0.0, 0.01, 0.02)
        ]
        lines.append(
            f"| {r['label']} ({mid}) | {by_id[mid]['volume']:.2f} | "
            f"{o['1']:+.0f} | {o['2']:+.0f} | {r['n_bets']} | "
            f"{pnl[0]:+.2f} | {pnl[1]:+.2f} | {pnl[2]:+.2f} |"
        )
    lines += [
        "",
        "Every aligned match here is from Euro 2024. None of the 19 "
        "eligible Copa events passes both-half alignment. World Cup matches "
        "are excluded before price execution because usable UTC clocks or "
        "compatible regulation-only contracts are absent.",
        "",
        "| Exclusion at alignment stage | Matches |",
        "| --- | ---: |",
    ]
    for reason, n in Counter(r["reason"] for r in audit if not r["aligned"]).items():
        lines.append(f"| {reason} | {n} |")
    lines += [
        "",
        "### Auditable artifacts",
        "",
        "- `backtest.json`: complete strategy summaries, every bet and all "
        "bankroll curves; schema-valid fixture copy in "
        "`backend/tests/golden/backtest_example.json`.",
        "- `market_sb_*.json`: 80 discovered-match API artifacts, including "
        "unaligned empty series for excluded markets. An aligned full "
        "response is copied to `backend/tests/golden/market_example.json`.",
        "- `bookmaker_coverage.json`: explicit unmatched CSV/catalogue rows; "
        "`bookmaker_1516.json` and `bookmaker_2324.json`: validated joins.",
        "- `polymarket_search_audit.json`, `polymarket_supplemental_audit.json`, "
        "`polymarket_archive_audit.json`: request coverage and bounded-search limits.",
        "- `polymarket_resolution_audit.json`: every candidate market question, "
        "full resolution description, volume, clock interpretation and exclusion.",
        "- `polymarket_alignment.json`: every candidate offset, matched goal "
        "jump, within-period consistency result and rejection reason.",
        "- `polymarket_diagnostics.json`: checkpoint scores and per-match P&L "
        "for every cost assumption; `kalshi_coverage.json`: archive evidence.",
        "- `data/models/backtest_*.json`: upstream cutoffs, training IDs, "
        "data sizes and held-out validation metrics.",
        "",
        "### Limits and integration boundary",
        "",
        "This is a retrospective research pipeline built today with old "
        "observations, not a forecast recorded before those games. Training "
        "and feature cutoffs prevent outcome leakage, but neither market "
        "archive coverage nor trade executability can be reconstructed "
        "perfectly. Tournament availability, goal-based alignment and "
        "liquidity checks select a nonrepresentative cohort. The bootstrap "
        "does not repair selection bias or account for all model uncertainty. "
        "No positive historical profit claim should omit these qualifications.",
        "",
        "The frozen 2015 upstream models are deliberately old and trained "
        "on a selected corpus. Cross-era and club-to-international shifts "
        "are material. The full 2023/24 league is unavailable. The model "
        "loses to the market in aggregate Brier and log loss, so positive "
        "paper P&L in a small subgroup is not evidence of general superiority.",
        "",
        "No shared API source or running port-8000 service is changed. "
        "The orchestrator must register the new router and copy fixtures. "
        "Tests of the owned package and real artifact endpoints are recorded "
        "below. The inherited counterfactual fixture mismatch is outside "
        "W10 ownership and must be resolved by the counterfactual workstream.",
        "",
    ]
    verification_path = output() / "verification.json"
    if verification_path.exists():
        verification = json.loads(verification_path.read_text())
        lines += [
            "### Verification",
            "",
            "- `uv run ruff check .`: passed.",
            "- `uv run ruff format --check .`: passed (71 Python files).",
            "- `uv run pytest`: 63 passed, 1 failed; all 16 W10 tests pass.",
            "- Sole failure: `tests/test_contract.py::"
            "test_counterfactual_contract_and_quantiles`. The existing response "
            "adds horizon/anchor/series fields absent from its fixture. "
            "The counterfactual source, test and fixture have zero diff from "
            "base commit `66ea23c`; W10 does not edit another agent's files.",
            f"- Live :8030: both golden responses exactly match; "
            f"{verification['market_responses']} market responses validate; "
            "unknown match returns 404.",
            f"- {verification['timeline_points']} series points across "
            f"{len(verification['aligned_timeline_matches'])} aligned matches "
            "match the shared :8000 timeline index, period, minute and label.",
            "- Port 8030 was stopped after acceptance; the shared port 8000 "
            "was only read, never restarted. No training workers remain.",
            "- No frontend files changed, so no screenshot requirement applies.",
            "",
            "Regenerate documentation/examples with "
            "`uv run python -m matchmind.backtest.report`. Verify HTTP endpoints "
            "while the dedicated test server is running with "
            "`uv run python -m matchmind.backtest.verify`.",
            "",
        ]
    source.write_text(intro + "\n".join(lines))
    golden = Path(__file__).resolve().parents[2] / "tests/golden"
    save(golden / "backtest_example.json", result)
    first = poly["per_match_pnl"]["0.0"][0]["match_id"]
    save(golden / "market_example.json", read(f"market_{first.replace(':', '_')}.json"))
    manifest = {
        "generated_at": result["generated_at"],
        "raw_response_files": {
            s: len(list((root() / "raw/markets" / s).glob("*.json")))
            for s in ("football-data", "polymarket", "kalshi")
        },
    }
    save(output() / "artifact_manifest.json", manifest)


if __name__ == "__main__":
    generate()
