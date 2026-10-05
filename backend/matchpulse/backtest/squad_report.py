"""Generate W12 documentation and the two explicitly authorized golden snapshots."""

# Keep generated prose paragraph-aligned for review.
# ruff: noqa: E501

import json
import shutil
from pathlib import Path

import pandas as pd

from matchpulse.backtest.common import output, root, save

MARKER = "\n## W12 player-informed models\n"


def table(headers: list[str], rows: list[list]) -> str:
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def main() -> None:
    pre = json.loads((root() / "models/backtest_squad_prematch.json").read_text())
    live = json.loads((root() / "models/backtest_inplay_squad.json").read_text())
    active = json.loads((output() / "w12/backtest.json").read_text())
    candidate = json.loads((output() / "squad_candidate_backtest.json").read_text())
    before = json.loads((output() / "w12_before/backtest.json").read_text())
    provenance = json.loads((output() / "squad_provenance.json").read_text())
    coverage = pd.read_parquet(output() / "squad_coverage.parquet")
    sections = [
        MARKER,
        f"Generated from artifacts: `{active['generated_at']}`. W12 explicitly adds a player-model workstream to the older PLAN ownership table. W11 supplies identities; W12 never changes its files.",
        "### Features and leakage boundaries",
        "CC0 Transfermarkt players, player_valuations, games, game_lineups, appearances and clubs are cached under `data/raw/players/transfermarkt/`. Club joins use date, both clubs and explicit name aliases, never scores. Reconstructed Bundesliga dates come from the already-validated bookmaker join. International XIs come from StatsBomb and W11 identities with confidence ≥0.8; unmatched players stay missing.",
        "Pre-match features are home-minus-away differences and mean levels of log(1 + total XI euros), mean log(1 + player euros), log bench value, age at match date, observed earlier international appearances, value of missing usual starters, inferred new-signing share and valuation coverage. Every valuation must be dated strictly before the match; same-day values are excluded. No present-day value, caps, current club or contract snapshot enters a model.",
        "Usual starters started at least three of the team’s previous five observed games, all dated before this match. Clubs use TM lineup history; internationals use prior StatsBomb XIs. Observed caps are the larger of prior TM and SB international appearance counts, a conservative lower bound rather than lifetime caps. Signing share is an imperfect proxy: a player’s first earlier observed appearance at this club must be within 180 days, with an earlier different club observed; established players have at least 180 days at this club. Unknowns stay missing. This is unavailable for national-team selection.",
        "The pre-match candidate is a regularized multinomial correction to the existing walk-forward rating logits. Value, value+age and all-feature sets, with L2 penalties 10 or 100, are scored only on weeks 6–17. Each tuning round fits only earlier rounds. The correction freezes after week 17 while the original ratings continue their established previous-round updates. Missing-value medians and scales use fitting rows only. The original threshold grid and tuning-profit rule are unchanged.",
        "The in-play candidate keeps the incumbent LightGBM parameters and adds log on-pitch value difference plus coverage. Player membership changes only after an observed substitution or on-pitch red card; bench dismissals do not remove active players. All values remain frozen at kickoff. A strength difference is missing unless both sides have values for at least 80% of current players. Strict minute boundaries, the three-minute trading lag, chronological training/calibration/validation partitions, and all tournament exclusions are unchanged.",
        "Candidate selection and retention are distinct. Feature/parameter selection uses tuning data only. Per the requested keep-the-better-model rule, replacement requires both held-out log loss and Brier to improve. The pre-match retention gate therefore uses weeks 18–34 once; it is a post-evaluation deployment decision, not an untouched evaluation of a preselected winner. In-play retention uses the existing 2020–2022 validation partition; tournament results never decide retention. No candidates were retuned after their held-out results.",
        f"Retained pre-match: **{'player-informed candidate' if pre['accepted'] else 'original model'}**. Retained in-play: **{'player-informed candidate' if live['squad_accepted'] else 'original model'}**.",
        f"Selected pre-match feature set: `{pre['selected']['feature_set']}`, L2 `{pre['selected']['penalty']}`. Candidate threshold `{pre['threshold']}`, original threshold `{pre['before_threshold']}`. W11 accepted identities: {provenance['w11_mapped_players']}; TM game joins: {provenance['matched_games']}/{provenance['matches']}.",
        "### Held-out probability scores (lower is better)",
    ]
    rows = []
    for split, metrics in [
        ("Pinnacle, weeks 18–34", pre["metrics"]),
        ("In-play validation", live["squad_metrics"]["validation"]),
        ("All excluded tournament minute rows", live["squad_metrics"]["tournaments"]),
    ]:
        for label, values in metrics.items():
            rows.append(
                [split, label, f"{values['log_loss']:.6f}", f"{values['brier']:.6f}"]
            )
    sections.append(table(["Partition", "Predictor", "Log loss", "Brier"], rows))
    sections += [
        "### Polymarket checkpoint scores",
        "Same aligned cohort and three-minute information lag. Market is normalized three-way historical trade prices; executable mid/ask quotes are unavailable.",
    ]
    old_diag = json.loads(
        (output() / "w12_before/polymarket_diagnostics.json").read_text()
    )
    new_diag = json.loads((output() / "w12/polymarket_diagnostics.json").read_text())
    rows = []
    for minute, entry in new_diag["calibration"].items():
        if not entry["n_matches"]:
            continue
        for label, source, key in [
            ("before", old_diag, "model"),
            ("candidate", candidate["polymarket_diagnostics"], "model"),
            ("retained", new_diag, "model"),
            ("market", new_diag, "market"),
        ]:
            score = source["calibration"][minute][key]
            rows.append(
                [
                    minute,
                    entry["n_matches"],
                    label,
                    f"{score['log_loss']:.6f}",
                    f"{score['brier']:.6f}",
                ]
            )
    sections.append(
        table(["Minute", "Matches", "Predictor", "Log loss", "Brier"], rows)
    )
    sections += [
        "### Before, candidate and retained backtests",
        "Identical stake rules, threshold-selection partition, slippage scenarios, settlement and 5,000-draw seed-2026 match-cluster bootstrap. Zero-bet evaluation matches stay in the bootstrap. Candidate results remain visible even when the original is retained. Opening odds remain payout sensitivities, not executable strategies. Pinnacle units and Polymarket dollars are separate.",
    ]
    rows = []
    for old, proposed, retained in zip(
        before["strategies"], candidate["strategies"], active["strategies"], strict=True
    ):
        assert old["id"] == proposed["id"] == retained["id"]
        for label, s in [
            ("before", old),
            ("candidate", proposed),
            ("retained", retained),
        ]:
            rows.append(
                [
                    s["id"],
                    label,
                    s["n_bets"],
                    f"{s['pnl']:+.2f}",
                    f"{s['roi']:.2%}",
                    f"[{s['roi_ci95'][0]:.2%}, {s['roi_ci95'][1]:.2%}]",
                    f"{s['brier_model']:.6f}",
                ]
            )
    sections.append(
        table(
            ["Strategy", "Version", "Bets", "P&L", "ROI", "ROI 95% CI", "Brier"], rows
        )
    )
    sections += [
        "### Feature coverage",
        "XI percentages use all 22 starting slots per match as denominator, including unmapped players. Live percentages additionally require a StatsBomb-to-TM identity for the starter. Entire historical competitions are shown so absent source eras cannot disappear from the denominator.",
    ]
    rows = []
    coverage_rows = []
    for (competition, season), group in coverage.groupby(
        ["competition", "season"], sort=True
    ):
        row = {
            "competition": competition,
            "season": season,
            "matches": int(group.match_id.nunique()),
            "tm_matched_matches": int(
                group.loc[group.tm_game.notna(), "match_id"].nunique()
            ),
            "xi_identity_coverage": float(group.mapped_xi.sum() / (11 * len(group))),
            "xi_valuation_coverage": float(group.valued_xi.sum() / (11 * len(group))),
            "live_xi_coverage": float(group.live_valued_xi.sum() / (11 * len(group))),
        }
        coverage_rows.append(row)
        rows.append(
            [
                competition,
                season,
                row["matches"],
                row["tm_matched_matches"],
                f"{row['xi_identity_coverage']:.1%}",
                f"{row['xi_valuation_coverage']:.1%}",
                f"{row['live_xi_coverage']:.1%}",
            ]
        )
    save(output() / "squad_coverage_summary.json", coverage_rows)
    sections.append(
        table(
            [
                "Competition",
                "Season",
                "Matches",
                "TM games",
                "XI identities",
                "Valued XI",
                "Live valued XI",
            ],
            rows,
        )
    )
    sections += [
        "### Limitations and integration",
        "Valuations are noisy estimates, not player ability or transfer prices. Historical rows were downloaded today and may have been retrospectively revised; strict dates do not establish archived publication vintages. W11 matching confidence is a heuristic, not a calibrated probability. Incomplete identities and valuations can bias summed strengths downward. The 80% live coverage guard limits but does not eliminate this. Missing history is not evidence of no international experience or no absences. First observed club appearances are not verified signing dates. Current lifetime caps are deliberately excluded.",
        "The game-state model and its API are unchanged; the optional quantile experiment was not run. No claim of improved pinball loss or coverage is made. The same small selected Polymarket cohort, retrospective goal alignment and unproven fills remain material limitations. No new profitability conclusion can rely on paper P&L alone.",
        "The requested additive `comparison` and `model_versions` fields live in the strict backtest schema. All old fields and market response shapes remain. W12 writes served artifacts under `data/processed/backtest/w12/`; the new route prefers them. This prevents the old shared process from reading a payload its older strict schema rejects. The orchestrator must merge and reload the API to expose W12 on :8000. W12 does not restart it. The two authorized backend golden snapshots are regenerated; fixtures/ remains orchestrator-owned and needs the corresponding additive update.",
        "Reproduce: `DATA_DIR=/home/ubuntu/hackathon/data uv run --group models python -m matchpulse.backtest squads`, then `python -m matchpulse.backtest.squad_report`. The immutable `w12_before/` snapshot preserves original scores, predictions, strategy results and model bundle. Candidate predictions, candidate backtests, complete join/coverage audits and model JSON cards remain beside it. Models and data are gitignored.",
        "Verification is recorded in `data/processed/backtest/w12/verification.json`; run the full suite plus `pytest matchpulse/backtest/test_squads.py`. Use :8050 for acceptance and stop it afterwards.",
    ]
    verification = output() / "w12/verification.json"
    if verification.exists():
        evidence = json.loads(verification.read_text())
        if evidence.get("checks"):
            sections.append(
                "Executed acceptance: "
                + evidence["checks"]["full_suite"]
                + "; owned-file lint/format passed; "
                + str(evidence["market_responses"])
                + " market responses and "
                + str(evidence["series_points"])
                + " series points verified on :8050. "
                + str(evidence["original_served_artifacts_unchanged"])
                + " original served artifacts remain byte-identical. "
                + "Acceptance server stopped; shared :8000 never restarted."
            )
    content = "\n\n".join(sections) + "\n"
    directory = Path(__file__).resolve().parent
    for path in [directory / "BACKTEST.md", directory.parent / "models/MODELS.md"]:
        original = path.read_text().split(MARKER)[0]
        path.write_text(original.rstrip() + "\n" + content)
    golden = directory.parents[1] / "tests/golden"
    shutil.copy2(output() / "w12/backtest.json", golden / "backtest_example.json")
    example = json.loads((golden / "market_example.json").read_text())
    shutil.copy2(
        output() / f"w12/market_{example['match_id'].replace(':', '_')}.json",
        golden / "market_example.json",
    )
    print("Updated model/backtest documentation and two authorized golden snapshots")


if __name__ == "__main__":
    main()
