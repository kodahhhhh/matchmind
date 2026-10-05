"""Recent lite pre-match backtest: atomic daily, strictly earlier-date updates."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from matchpulse.backtest.prematch import result_probability
from matchpulse.models.common import catalogue, data_dir, timestamp
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import (
    compare,
    file_hash,
    freeze_manifest,
    probability_metrics,
)


def rolling_predictions(
    matches: pd.DataFrame, *, decay: float = 0.95, prior: float = 8.0
) -> pd.DataFrame:
    """Same frozen W10 team-rating recipe, alternate historical signal only.

    Predict an entire date before updating any teams or league counts. Teams are
    source-local IDs. The naive comparator is prior-smoothed league result rate.
    """
    history = {k: defaultdict(list) for k in ("legacy", "shot", "goals")}
    league = defaultdict(
        lambda: {
            "n": 0,
            "h": 0.0,
            "a": 0.0,
            "outcomes": np.array([4.5, 2.7, 2.8]),
            "last": None,
        }
    )
    records = []
    for date, group in matches.sort_values(["match_date", "match_id"]).groupby(
        "match_date", sort=True
    ):
        for row in group.to_dict("records"):
            comp = row["competition"]
            state = league[comp]
            lh, la = (
                (15 + state["h"]) / (10 + state["n"]),
                (12 + state["a"]) / (10 + state["n"]),
            )
            mean = (lh + la) / 2
            record = {
                "match_id": row["match_id"],
                "date": date,
                "competition": comp,
                "train_end_date": state["last"],
                "training_matches": state["n"],
                "result": 0
                if row["home_score"] > row["away_score"]
                else 1
                if row["home_score"] == row["away_score"]
                else 2,
                "naive": (state["outcomes"] / state["outcomes"].sum()).tolist(),
            }
            for signal in history:
                ratings = []
                for side in ("home", "away"):
                    games = history[signal][(comp, row[side]["id"])]
                    weights = decay ** np.arange(len(games) - 1, -1, -1)
                    ratings.append(
                        tuple(
                            (
                                prior * mean
                                + sum(
                                    g[j] * w
                                    for g, w in zip(games, weights, strict=True)
                                )
                            )
                            / (prior + weights.sum())
                            / mean
                            for j in (0, 1)
                        )
                    )
                record[signal] = result_probability(
                    np.clip(lh * ratings[0][0] * ratings[1][1], 0.15, 5),
                    np.clip(la * ratings[1][0] * ratings[0][1], 0.15, 5),
                ).tolist()
            records.append(record)
        for row in group.to_dict("records"):
            comp = row["competition"]
            for signal in history:
                h, a = (
                    (row["home_score"], row["away_score"])
                    if signal == "goals"
                    else (row[f"{signal}_home"], row[f"{signal}_away"])
                )
                history[signal][(comp, row["home"]["id"])].append((h, a))
                history[signal][(comp, row["away"]["id"])].append((a, h))
            state = league[comp]
            state["n"] += 1
            state["h"] += row["home_score"]
            state["a"] += row["away_score"]
            state["outcomes"][
                0
                if row["home_score"] > row["away_score"]
                else 1
                if row["home_score"] == row["away_score"]
                else 2
            ] += 1
            state["last"] = date
    return pd.DataFrame(records)


def run(out: Path) -> dict:
    root = data_dir()
    source = root / "models/candidates/xg-shot-v1"
    paths = [source / f"understat_{name}.parquet" for name in ["shots", "matches"]]
    paths += [source / "xg_shot.txt", source / "split.json"]
    matches, shots = pd.read_parquet(paths[1]), pd.read_parquet(paths[0])
    latest = max(m["match_date"] for m in catalogue() if m["match_date"])
    if latest >= matches.match_date.min():
        raise ValueError(
            "Shot-only upstream training is not strictly earlier than recent matches"
        )
    freeze_manifest(
        out / "split.json",
        {
            "protocol": "daily folds; atomic date updates; fixed W10 .95/8/1 recipe",
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in paths},
            "upstream_latest_match_date": latest,
            "evaluation_start": "2026-01-01",
            "warmup": "2025-08-15 through 2025-12-31",
            "folds": sorted(matches.match_date.unique().tolist()),
            "market": "No cached recent closing odds; unavailable",
        },
    )
    if (out / "backtest_lite_prematch.json").exists():
        raise ValueError("Completed candidate exists")
    totals = shots.groupby(["match_id", "team"])[["xg", "legacy_xg"]].sum()
    for side in ["home", "away"]:
        part = totals.xs(side, level="team")
        for name, column in [("shot", "xg"), ("legacy", "legacy_xg")]:
            matches[f"{name}_{side}"] = matches.match_id.map(part[column]).fillna(0.0)
    rows = rolling_predictions(matches)
    if not ((rows.train_end_date.isna()) | (rows.train_end_date < rows.date)).all():
        raise ValueError("Future results entered a daily fold")
    rows.to_parquet(out / "predictions.parquet", index=False)
    test = rows[rows.date >= "2026-01-01"]
    y, groups = test.result.to_numpy(), test.match_id.to_numpy()
    q = np.array(test.shot.tolist())
    results = {
        name: compare(y, np.array(test[name].tolist()), q, groups)
        for name in ["legacy", "naive", "goals"]
    }
    monthly = {
        month: {
            "n_matches": len(g),
            "candidate": probability_metrics(
                g.result.to_numpy(), np.array(g.shot.tolist())
            ),
            "naive": probability_metrics(
                g.result.to_numpy(), np.array(g.naive.tolist())
            ),
        }
        for month, g in test.groupby(test.date.str[:7])
    }
    result = {
        "training_date": timestamp(),
        "n_matches": len(matches),
        "n_test_matches": len(test),
        **results["legacy"],
        "vs_naive": results["naive"],
        "vs_goals_only": results["goals"],
        "monthly": monthly,
        "params": {"decay": 0.95, "prior": 8.0, "xg_weight": 1.0},
        "baseline_definition": "W10 recipe with current lite xG; not W12 squad parity",
        "validation": "strict daily folds, monthly reports; no selection on evaluation",
        "market": {
            "status": "unavailable",
            "reason": "No recent matched closing odds in local inputs",
        },
        "promotion_recommended": False,
    }
    write_report(out / "backtest_lite_prematch.json", result)
    print(
        json.dumps({k: result[k] for k in ["n_test_matches", "paired_ci"]}, indent=2),
        flush=True,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="prematch-lite-v1")
    run(destination(parser.parse_args().run))


if __name__ == "__main__":
    main()
