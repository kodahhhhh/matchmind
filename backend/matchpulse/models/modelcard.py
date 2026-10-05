"""Render the committed model card directly from measured local reports."""

# Long prose strings deliberately map to whole Markdown paragraphs.
# ruff: noqa: E501
import json
from pathlib import Path
from typing import Any

from matchpulse.models.common import data_dir


def table(headers: list[str], rows: list[list[Any]]) -> str:
    def fmt(v: Any) -> str:
        return f"{v:.6f}" if isinstance(v, float) else str(v)

    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *["| " + " | ".join(map(fmt, row)) + " |" for row in rows],
        ]
    )


def main() -> None:
    reports = {
        name: json.loads((data_dir() / f"models/{name}.json").read_text())
        for name in [
            "spadl",
            "xg",
            "vaep",
            "xt",
            "vaep_sanity",
            "backfill",
            "gamestate",
        ]
    }
    spadl, xg, vaep, xt, sanity, backfill, game = [reports[n] for n in reports]
    verification = json.loads((data_dir() / "models/verification.json").read_text())
    repeat = json.loads((data_dir() / "models/backfill_sb_3869685.json").read_text())
    lines = [
        "# MatchPulse custom models",
        "",
        f"Measured training run: {game['training_date']}. CPU only. StatsBomb open-data source commit `4b73468`; catalogue, not the incomplete source match index, selects the corpus.",
        "",
        "## Data, reproducibility and validation",
        "",
        f"{spadl['n_matches']:,} men’s matches; {spadl['n_actions']:,} SPADL actions; {len(spadl['failures'])} conversion failures. The 493 demo matches are a subset of training, and all corpus xG, VAEP and xT outputs are held out by match. Synthetic SPADL dribbles have no raw UUID and are excluded from the DB join. Split interception/pass actions are summed back to one raw UUID. Stored SPADL has home attacking +x; spatial training rotates each acting team to +x. DB raw coordinates are unchanged.",
        "",
        "Five deterministic shuffled match folds (seed 2026) are shared across models. No action-level random split. Shootouts receive held-out xG/VAEP predictions for event completeness, but are excluded from training, evaluation, rankings, windows and timeline sums. Finals below exclude shootouts. All artifacts remain gitignored. Final models fit all eligible training matches; match artifacts use held-out models.",
        "",
        "The `models` dependency group pins socceraction 1.5.3 and multimethod <2 for its pandera compatibility. Python 3.12, pandas 2, LightGBM 4, NumPy 1.26. Runtime models need the models group installed. No provider/network requests are used to train.",
        "",
        "```sh",
        "cd backend",
        "export DATA_DIR=/home/ubuntu/hackathon/data",
        "uv sync --group models",
        "uv run --group models python -m matchpulse.models.spadl",
        "uv run --group models python -m matchpulse.models.xg",
        "uv run --group models python -m matchpulse.models.vaep",
        "uv run --group models python -m matchpulse.models.xt",
        "uv run --group models python -m matchpulse.models.sanity",
        "uv run --group models python -m matchpulse.models.backfill",
        "uv run --group models python -m matchpulse.models.backfill --match-id sb:3869685",
        "uv run --group models python -m matchpulse.db.load refresh",
        "uv run --group models python -m matchpulse.models.gamestate_train",
        "uv run --group models python -m matchpulse.models.verify",
        "uv run --group models python -m matchpulse.models.modelcard",
        "```",
        "",
        "VAEP uses a disk-backed float32 feature matrix to avoid holding several complete copies in RAM. Game-state caches are fingerprinted against upstream training reports and window/feature definitions and are rebuilt when these change.",
        "",
        "## xG",
        "",
        f"LightGBM binary classifier; {xg['n_shots']:,} non-shootout shots across {xg['n_matches']:,} matches. Features: distance; visible goal-mouth angle; position; body part; shot type; technique; first-time; pressure; related-pass through ball/cross/cut-back/set piece; freeze-frame availability; opponents inside the triangular shot cone; keeper availability, distance from goal line and perpendicular distance from the shot-to-goal-centre line; pre-shot score difference and minute. Missing keepers remain missing, not zero. Neither shot endpoint/outcome nor StatsBomb xG is a feature.",
        "",
        "Uncalibrated held-out probabilities are retained: calibration deciles and total expected goals are already close to observed goals. No calibrator was fitted to evaluation labels. StatsBomb’s benchmark is evaluated on exactly the same shots; its original training overlap is unknown, so this is a reference comparison rather than proof of superiority.",
        "",
        table(
            ["Held-out metric", "MatchPulse", "StatsBomb"],
            [
                [metric, xg["same_shots_ours"][metric], xg["statsbomb"][metric]]
                for metric in ["log_loss", "brier", "auc", "total_xg", "goals"]
            ],
        ),
        "",
        "Each model’s deciles are sorted by its own prediction (equal-count groups).",
        "",
        table(
            [
                "Decile",
                "N",
                "Our mean xG",
                "Our goal rate",
                "SB mean xG",
                "SB goal rate",
            ],
            [
                [
                    i + 1,
                    a["n"],
                    a["predicted"],
                    a["observed"],
                    b["predicted"],
                    b["observed"],
                ]
                for i, (a, b) in enumerate(
                    zip(
                        xg["metrics"]["calibration_deciles"],
                        xg["statsbomb"]["calibration_deciles"],
                        strict=True,
                    )
                )
            ],
        ),
        "",
        "## VAEP",
        "",
        f"Two LightGBM classifiers, socceraction’s standard {len(vaep['features'])} features from three game states, and scores/concedes labels over ten actions (including the current action). {vaep['n_training_actions']:,} non-shootout actions. Histories and labels reset between periods. Post-action result is intentionally observed: this values completed actions and is not a pre-shot scoring forecast. Reported AUC partly benefits from recognizing already-scored goals.",
        "",
        table(
            ["Target", "Held-out AUC", "Held-out Brier", "Base rate"],
            [
                [t, m["auc"], m["brier"], m["base_rate"]]
                for t, m in vaep["metrics"].items()
            ],
        ),
        "",
        "Values use socceraction’s offensive/defensive differences, its ten-second phase reset, and its fixed penalty (0.792453) and corner (0.046500) prior constants. These are library conventions, not our xG predictions. `vaep_value = offensive_value + defensive_value`. This is action attribution, not an estimate of a player’s causal contribution.",
        "",
        "### Player sanity check",
        "",
        "Top 20 VAEP per 90, at least 900 observed minutes. Minutes include stoppage and extra time, reconstructed from starting XIs, substitutions and on-pitch dismissals. This corpus overrepresents Barcelona/Messi and selected teams/seasons; rankings are not a population-wide best-player claim.",
        "",
        table(
            ["Player", "Minutes", "Total VAEP", "VAEP / 90"],
            [
                [p["name"], p["minutes"], p["vaep"], p["vaep_per90"]]
                for p in sanity["top20_per90_min900"]
            ],
        ),
        "",
        "### World Cup 2022 final goals",
        "",
        table(
            ["Minute", "Period", "Player", "Action", "Offensive", "Defensive", "VAEP"],
            [
                [
                    a["minute"],
                    a["period_id"],
                    a["name"],
                    a["type_name"],
                    a["offensive_value"],
                    a["defensive_value"],
                    a["vaep_value"],
                ]
                for a in sanity["final_goals"]
            ],
        ),
        "",
        "### World Cup 2022 final top 20 actions",
        "",
        table(
            ["Minute", "Player", "Action", "Result", "VAEP", "SPADL action index"],
            [
                [
                    a["minute"],
                    a["name"],
                    a["type_name"],
                    a["result_name"],
                    a["vaep_value"],
                    a["action_id"],
                ]
                for a in sanity["final_top20_actions"]
            ],
        ),
        "",
        "## xT",
        "",
        f"socceraction ExpectedThreat, 12×8 cells, fitted on the non-shootout actions (moves plus shots to estimate move/shot choice and scoring probabilities). {xt['n_rated_moves']:,} successful moves receive held-out destination-minus-origin values. Unsuccessful moves and non-moves remain NULL; negative move values are retained. Five match-held-out grids generate action outputs; the final all-match grid and fold grids are in `data/models/xt.json`. No predictive performance claim is made for this descriptive grid.",
        "",
        "## Database backfill",
        "",
        f"{backfill['n_matches']} demo matches; {backfill['n_model_rows']:,} UUID-keyed model rows; missing goal-shot xG: {backfill['missing_goal_xg']}. The join is `events.extra->>'id' = original_event_id`, scoped by match. Temporary COPY plus one UPDATE FROM; repeated values are skipped. Raw reloads reset model columns; rerun backfill and refresh. The CLI takes optional `--match-id sb:3869685`.",
        "",
        table(
            [
                "Raw type",
                "Raw rows",
                "UUID matches",
                "Match rate",
                "VAEP rows",
                "xG rows",
                "xT rows",
            ],
            [
                [
                    r["type"],
                    r["raw_events"],
                    r["joined"],
                    r["joined"] / r["raw_events"],
                    r["vaep"],
                    r["xg"],
                    r["xt"],
                ]
                for r in backfill["coverage_by_type"]
            ],
        ),
        "",
        "SPADL deliberately excludes raw non-actions such as pressure, ball receipt, lineup and substitutions. Their missing VAEP is intentional, not zero-valued model output. Omitted passes are source-labelled Unknown or Injury Clearance, which socceraction treats as outside play.",
        "",
        "## Game-state model: modelled, not causal",
        "",
        f"Nine LightGBM quantile regressors: p10/p50/p90 for next-15-minute xG for, xG against and possession share. {game['n_windows']:,} five-minute team-perspective windows; {game['n_training_windows']:,} complete-horizon training/evaluation rows across {game['n_matches']:,} matches. {game['n_censored_windows']:,} late/censored or no-pass future rows remain in the window artifact but are not fitted or scored.",
        "",
        "The complete stack is held out: for each outer match fold, xG/VAEP predictors exclude that fold and regenerate both training and test windows. Final models fit all-match OOF windows. Overlapping windows and paired team perspectives never cross match folds. This is retrospective random-match evaluation, not a forward-season generalization test.",
        "",
        "Histories are five minutes within a period. Period timestamps concatenate actual playing-clock durations, including stoppage but excluding interval breaks and shootouts. Future horizons can cross half-time. Possession is a **pass-count share proxy**, matching the raw DB convention, not tracked possession time. Field tilt is share of actions beginning beyond 70 metres; an empty denominator yields 0.5 and is not evidence of equal control. Targets are model xG sums, not actual future goals.",
        "",
        "Inference contract: `featurize(window_rows)` selects the ordered feature list below and rejects missing/nonfinite inputs. `predict(features)` returns `{target: {p10: [values], p50: [values], p90: [values]}}`, with one aligned value per row. Quantiles are rearranged to remove crossings and clipped to physical support. The API must use the same five-minute feature definitions. Features:",
        "",
        "`" + ", ".join(game["features"]) + "`",
        "",
        table(
            [
                "Target",
                "p10 loss",
                "p50 loss",
                "p90 loss",
                "p10–p90 coverage",
                "Mean width",
                "Zero outcomes",
            ],
            [
                [
                    t,
                    m["pinball"]["p10"],
                    m["pinball"]["p50"],
                    m["pinball"]["p90"],
                    m["coverage_p10_p90"],
                    m["mean_width"],
                    m["zero_outcomes"],
                ]
                for t, m in game["metrics"].items()
            ],
        ),
        "",
        "Coverage is inclusive, evaluated against held-out outcomes; zero-inflated xG targets need not achieve exactly 80% with deterministic quantiles. Bands describe outcome spread, not confidence intervals on a causal effect.",
        "",
        table(
            ["Target", "State", "N", "Coverage", "Mean band width"],
            [
                [t, state, m["n"], m["coverage_p10_p90"], m["mean_width"]]
                for t, values in game["metrics"].items()
                for state, m in values["by_state"].items()
            ],
        ),
        "",
        "### Confounding diagnostic",
        "",
        game["confounding_diagnostic"]["definition"],
        "",
        table(
            ["Diagnostic", "xG"],
            [
                [k, v]
                for k, v in game["confounding_diagnostic"].items()
                if k != "definition"
            ],
        ),
        "",
        "**Goals, substitutions and dismissals are not random.** Strong teams lead more, chasing teams attack differently, and coaches substitute because of fatigue, injury and tactical problems that are only partly observed. Changing score difference while holding recent xG/VAEP fixed creates an artificial state; it does not remove the goal’s downstream consequences. `no_sub` must restore the prior substitution age (or elapsed minutes if none), and `remove_red_card` restores only the affected player count. These are modelled sensitivities. Display analogs and the caveat prominently; never claim what would have happened.",
        "",
        "## Artifacts and integration",
        "",
        "- `processed/spadl/{native_id}.parquet`, `_index.parquet`: all actions, catalogue home team, original UUIDs.",
        "- `processed/xg/shots.parquet`: features, labels, StatsBomb benchmark, fold and held-out xG, including separately identified shootouts.",
        "- `processed/vaep/{native_id}.parquet`: actions, fold, held-out probabilities and three action values.",
        "- `processed/xt/{native_id}.parquet`: action/UUID keys and held-out xT.",
        "- `processed/gamestate_windows.parquet`: all-match OOF features/outcomes and match metadata. Use only complete horizons when displaying 15-minute analog outcomes.",
        "- `processed/gamestate_oof.parquet`: honest outer-fold evaluation predictions/outcomes.",
        "- `models/{xg,vaep,xt,gamestate}.json`: machine-readable metrics, sizes, features and provenance; LightGBM text models alongside.",
        "",
        "API workstream: import `gamestate_model.featurize/predict`, select the team perspective and apply the documented feature edit. Load the 2,924-match window artifact for analogs; do not imply those non-demo matches have DB event replay. Refresh/recompute downstream sequence danger and rankings after backfill as appropriate. No schema or fixture shapes were changed.",
        "",
        "## Verification",
        "",
        "`uv run --group models ruff check .`, `ruff format --check .`, and the 11 tests in `tests/test_models*.py` pass. Checks cover freeze-frame geometry, match folds, cross-half score context, UUID aggregation, synthetic-action exclusion, the final's goal shots, all SPADL action types, window boundaries, goal-kick possession and forecast input contracts.",
        "",
        f"Read-only acceptance (`python -m matchpulse.models.verify`): {verification['counts']['matches']} DB matches, {verification['counts']['xg']:,} persisted shot xG values, {verification['counts']['vaep']:,} VAEP rows, {verification['counts']['xt']:,} xT rows. Final goal xG matches held-out artifacts, and refreshed final timeline xG/VAEP sums match raw event sums. The repeated final-match backfill changed {repeat['updated']} rows. Factual and modified-score predictions run through the saved-model inference API with finite ordered bands. Evidence: `data/models/verification.json`.",
        "",
        "## Remaining limits",
        "",
        "- StatsBomb open data is selected and historically uneven. Missing freeze frames and reconstructed metadata vary by era; random match folds do not establish unseen-team or future-season performance.",
        "- No tracking data, off-ball movement valuation, fatigue/injury measurements or causal identification. SPADL conventions and proxy possession limit interpretation. Own-goal labels follow socceraction and can omit non-shot own goals. Counterfactuals preserve the observed horizon; they do not resimulate whether extra time occurs.",
        "- Known-corpus xG/VAEP/xT comes from OOF artifacts. Forecast validation is outer-held-out; final game-state inference on known historical windows is in-sample modelled sensitivity. Do not substitute final-model predictions into validation or claim out-of-sample deployment evidence.",
        "- Quantile coverage is empirical for this corpus and the documented window clock/proxies. All final-model future performance remains unverified.",
        "",
    ]
    Path(__file__).with_name("MODELS.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
