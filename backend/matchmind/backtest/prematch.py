"""Frozen historical xG plus strictly previous-round Poisson team ratings."""

import json
from collections import defaultdict
from itertools import product

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import poisson

from matchmind.backtest.common import catalogue, output, root, save
from matchmind.backtest.statistics import OUTCOMES, scores, summary
from matchmind.models.xg import FEATURES


def historical_xg() -> pd.DataFrame:
    path = output() / "prematch_xg.parquet"
    if path.exists():
        return pd.read_parquet(path)
    shots = pd.read_parquet(root() / "processed/xg/shots.parquet")
    prior = {
        m["native_id"]
        for m in catalogue()
        if m["training"] and m["match_date"] and m["match_date"] < "2015-08-01"
    }
    train = shots.game_id.isin(prior) & (shots.period < 5)
    model = lgb.LGBMClassifier(
        n_estimators=200,
        learning_rate=0.035,
        num_leaves=15,
        min_child_samples=100,
        reg_lambda=5,
        n_jobs=4,
        verbosity=-1,
        random_state=2026,
    ).fit(shots.loc[train, FEATURES], shots.loc[train, "goal"])
    target = json.loads((output() / "bookmaker_1516.json").read_text())
    ids = {m["native_id"] for m in target}
    test = shots.game_id.isin(ids) & (shots.period < 3)
    result = shots.loc[test, ["game_id", "original_event_id"]].copy()
    result["xg"] = model.predict_proba(shots.loc[test, FEATURES])[:, 1]
    result.to_parquet(path, index=False)
    model_path = root() / "models/backtest_prematch_xg.txt"
    model.booster_.save_model(str(model_path))
    save(
        model_path.with_suffix(".json"),
        {
            "training_date": pd.Timestamp.now(tz="UTC").isoformat(),
            "n_matches": len(prior),
            "n_shots": int(train.sum()),
            "cutoff": "2015-08-01",
            "training_match_ids": sorted(prior),
            "validation": (
                "Entire Bundesliga 2015/16 held out; frozen before first "
                "match. No test calibration."
            ),
            "metrics": {
                "heldout_brier": float(
                    np.mean((result.xg.to_numpy() - shots.loc[test, "goal"]) ** 2)
                )
            },
        },
    )
    return result


def season() -> list[dict]:
    rows = json.loads((output() / "bookmaker_1516.json").read_text())
    if len(rows) != 306:
        raise ValueError("Require complete 306-match season before evaluation")
    xg = historical_xg().set_index("original_event_id").xg
    for row in rows:
        actions = pd.read_parquet(
            root() / f"processed/spadl/{row['native_id']}.parquet"
        )
        actions = actions[actions.period_id < 3].copy()
        actions["xg"] = actions.original_event_id.map(xg).fillna(0)
        # Original shot UUIDs occur once as shots in SPADL.
        shots = actions[
            actions.type_name.isin(["shot", "shot_penalty", "shot_freekick"])
        ]
        row["xg_home"] = float(
            shots.loc[shots.team_id == row["home"]["id"], "xg"].sum()
        )
        row["xg_away"] = float(
            shots.loc[shots.team_id == row["away"]["id"], "xg"].sum()
        )
    # CSV is chronological, full nine-game rounds verified by unique teams.
    for week in range(1, 35):
        group = [r for r in rows if r["round"] == week]
        if len({r[s]["id"] for r in group for s in ("home", "away")}) != 18:
            raise ValueError(f"CSV grouping is not a complete matchweek: {week}")
        if any(r["matchweek"] is not None and r["matchweek"] != week for r in group):
            raise ValueError(f"Catalogue round mismatch: {week}")
    return rows


def result_probability(home_rate: float, away_rate: float) -> np.ndarray:
    h = poisson.pmf(np.arange(25), home_rate)
    a = poisson.pmf(np.arange(25), away_rate)
    matrix = h[:, None] * a[None, :]
    p = np.array(
        [np.tril(matrix, -1).sum(), np.trace(matrix), np.triu(matrix, 1).sum()]
    )
    return p / p.sum()


def predictions(
    rows: list[dict], decay: float, prior: float, xg_weight: float
) -> np.ndarray:
    history = defaultdict(list)
    probabilities = []
    # Fixed priors, never estimated from the evaluation season.
    league_home, league_away = 1.5, 1.2
    for week in range(1, 35):
        group = [r for r in rows if r["round"] == week]
        previous = [r for r in rows if r["round"] < week]
        if previous:
            league_home = (15 + sum(r["home_score"] for r in previous)) / (
                10 + len(previous)
            )
            league_away = (12 + sum(r["away_score"] for r in previous)) / (
                10 + len(previous)
            )
        league = (league_home + league_away) / 2
        for row in group:
            ratings = []
            for side in ("home", "away"):
                games = history[row[side]["id"]]
                w = decay ** np.arange(len(games) - 1, -1, -1)
                att = (
                    prior * league
                    + sum(v[0] * z for v, z in zip(games, w, strict=True))
                ) / (prior + w.sum())
                defence = (
                    prior * league
                    + sum(v[1] * z for v, z in zip(games, w, strict=True))
                ) / (prior + w.sum())
                ratings.append((att / league, defence / league))
            probabilities.append(
                result_probability(
                    np.clip(league_home * ratings[0][0] * ratings[1][1], 0.15, 5),
                    np.clip(league_away * ratings[1][0] * ratings[0][1], 0.15, 5),
                )
            )
        # Atomic round update: no result from this round can affect another match.
        for row in group:
            h = xg_weight * row["xg_home"] + (1 - xg_weight) * row["home_score"]
            a = xg_weight * row["xg_away"] + (1 - xg_weight) * row["away_score"]
            history[row["home"]["id"]].append((h, a))
            history[row["away"]["id"]].append((a, h))
    return np.array(probabilities)


def train() -> None:
    rows = season()
    y = np.array(
        [
            0
            if r["home_score"] > r["away_score"]
            else 1
            if r["home_score"] == r["away_score"]
            else 2
            for r in rows
        ]
    )
    tuning = np.array([6 <= r["round"] <= 17 for r in rows])
    candidates = []
    for decay, prior, weight in product([0.85, 0.95], [3.0, 8.0], [0.5, 1.0]):
        p = predictions(rows, decay, prior, weight)
        candidates.append(
            {
                "decay": decay,
                "prior": prior,
                "xg_weight": weight,
                "log_loss": scores(y[tuning], p[tuning])["log_loss"],
            }
        )
    best = min(candidates, key=lambda c: c["log_loss"])
    p = predictions(rows, best["decay"], best["prior"], best["xg_weight"])
    thresholds = []
    for threshold in [0.0, 0.05, 0.1, 0.2]:
        bets = [
            (j, k)
            for j, r in enumerate(rows)
            if tuning[j]
            for k in range(3)
            if p[j, k] * r["closing"][k] - 1 > threshold
        ]
        profit = sum((rows[j]["closing"][k] if y[j] == k else 0) - 1 for j, k in bets)
        thresholds.append({"threshold": threshold, "n_bets": len(bets), "pnl": profit})
    selected = max(thresholds, key=lambda t: t["pnl"])
    save(
        output() / "prematch_selection.json",
        {
            "parameters": best,
            "candidates": candidates,
            "thresholds": thresholds,
            "threshold": selected["threshold"],
            "tune_rounds": [6, 17],
            "evaluation_rounds": [18, 34],
            "selection": (
                "Minimum tuning log loss, then maximum tuning flat profit; no"
                " evaluation optimization."
            ),
        },
    )
    for i, r in enumerate(rows):
        r["model"] = p[i].tolist()
        r["result"] = int(y[i])
    save(output() / "prematch_predictions.json", rows)
    print("Prematch frozen parameters", best, "threshold", selected, flush=True)


def run(
    predictions_file: str = "prematch_predictions.json",
    selection_file: str = "prematch_selection.json",
    publish: bool = True,
) -> tuple[list[dict], dict]:
    rows = json.loads((output() / predictions_file).read_text())
    selection = json.loads((output() / selection_file).read_text())
    rows = [r for r in rows if r["round"] >= 18]
    y = np.array([r["result"] for r in rows])
    p = np.array([r["model"] for r in rows])
    market = 1 / np.array([r["closing"] for r in rows])
    market /= market.sum(axis=1, keepdims=True)
    metrics = {"model": scores(y, p), "market": scores(y, market)}
    strategies = []
    for price, staking in product(["closing", "opening"], ["flat", "kelly"]):
        bankroll = 1000.0
        equity = [{"i": 0, "label": "Start", "bankroll": bankroll}]
        bets = []
        for week in range(18, 35):
            group = [r for r in rows if r["round"] == week]
            stake_basis = bankroll
            round_bets = []
            for r in group:
                for k, probability in enumerate(r["model"]):
                    odds = r[price][k]
                    # Opening is a labelled payout sensitivity on close-selected bets.
                    if probability * r["closing"][k] - 1 <= selection["threshold"]:
                        continue
                    stake = (
                        1.0
                        if staking == "flat"
                        else stake_basis
                        * min(
                            0.05, max(0, 0.25 * (probability * odds - 1) / (odds - 1))
                        )
                    )
                    if stake <= 0:
                        continue
                    round_bets.append(
                        {
                            "match_id": r["match_id"],
                            "label": f"{r['home']['name']} – {r['away']['name']}",
                            "outcome": OUTCOMES[k],
                            "side": "YES",
                            "price_or_odds": odds,
                            "model_prob": probability,
                            "market_prob": float(market[rows.index(r), k]),
                            "stake": stake,
                            "pnl": stake * ((odds if r["result"] == k else 0) - 1),
                            "clv": odds / r["closing"][k] - 1,
                        }
                    )
            # All round bets are reserved before settlement; no within-round
            # reinvestment.
            total = sum(b["stake"] for b in round_bets)
            scale = min(1.0, bankroll / total) if total else 1.0
            for b in round_bets:
                b["stake"] *= scale
                b["pnl"] *= scale
            bankroll += sum(b["pnl"] for b in round_bets)
            bets.extend(round_bets)
            equity.append(
                {"i": len(equity), "label": f"Matchweek {week}", "bankroll": bankroll}
            )
        data = summary(bets, [r["match_id"] for r in rows], equity)
        strategies.append(
            {
                "id": f"pinnacle-{price}-{staking}",
                "name": f"Pinnacle {price} · "
                + ("1 unit" if staking == "flat" else "quarter-Kelly")
                + (" (payout sensitivity only)" if price == "opening" else ""),
                "market": "pinnacle",
                "description": "Previous-round Poisson ratings; closing-selected bets. "
                + (
                    (
                        "Opening payouts are NOT an executable strategy: opening "
                        "timestamps unavailable and selection uses closing odds. "
                        "Excluded from historical profit claims."
                    )
                    if price == "opening"
                    else (
                        "Quarter-Kelly capped at 5% per bet; no within-round "
                        "reinvestment."
                    )
                ),
                "eval_period": "Bundesliga 2015/16 · matchweeks 18–34",
                **data,
                "clv": float(np.mean([b["clv"] for b in bets])) if bets else 0.0,
                "brier_model": metrics["model"]["brier"],
                "brier_market": metrics["market"]["brier"],
            }
        )
    if publish:
        save(output() / "prematch_metrics.json", metrics)
    return strategies, metrics
