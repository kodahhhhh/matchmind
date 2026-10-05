"""Rebuild candidate action values and player ranking sanity checks."""

import argparse
import json
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from socceraction.vaep.formula import value

from matchpulse.models.common import data_dir, fold_map
from matchpulse.models.evaluate import destination, write_report
from matchpulse.models.evaluation import file_hash, freeze_manifest


def run(out: Path) -> dict:
    """Materialize OOF candidate values and compare player rankings at fixed minutes."""
    root = data_dir()
    report = json.loads((out / "vaep.json").read_text())
    predictions = pd.read_parquet(out / "predictions.parquet")
    minutes_path = root / "processed/player_match_vaep.parquet"
    minutes = pd.read_parquet(minutes_path)
    freeze_manifest(
        out / "ranking_inputs.json",
        {
            "predictions_sha256": file_hash(out / "predictions.parquet"),
            "minutes_sha256": file_hash(minutes_path),
        },
    )
    assignment, totals = fold_map(), []
    (out / "vaep").mkdir(exist_ok=True)

    @lru_cache(maxsize=10)
    def booster(target: str, fold: int) -> lgb.Booster:
        return lgb.Booster(model_file=str(out / f"vaep_{target}_fold_{fold}.txt"))

    for i, (game, prob) in enumerate(predictions.groupby("game_id", sort=False)):
        actions = pd.read_parquet(root / f"processed/spadl/{game}.parquet")
        actions = actions.merge(
            prob[["game_id", "action_id", "candidate_scores", "candidate_concedes"]],
            on=["game_id", "action_id"],
            how="left",
            validate="one_to_one",
        )
        if actions.loc[actions.period_id < 5, "candidate_scores"].isna().any():
            raise ValueError(f"Missing candidate non-shootout values: {game}")
        missing = actions.period_id == 5
        if missing.any():
            features = pd.read_parquet(root / f"processed/vaep_features/{game}.parquet")
            features = features.set_index("action_id").loc[
                actions.loc[missing, "action_id"]
            ]
            for target in ("scores", "concedes"):
                actions.loc[missing, f"candidate_{target}"] = booster(
                    target, assignment[game]
                ).predict(features[report["features"]], num_threads=1)
        frames = []
        for _, period in actions.groupby("period_id", sort=False):
            period = period.reset_index(drop=True)
            values = value(period, period.candidate_scores, period.candidate_concedes)
            frames.append(pd.concat([period, values], axis=1))
        valued = pd.concat(frames, ignore_index=True)
        valued.to_parquet(out / f"vaep/{game}.parquet", index=False)
        t = (
            valued[valued.period_id < 5]
            .groupby("player_id")
            .vaep_value.sum()
            .reset_index()
        )
        t["game_id"] = game
        totals.append(t)
        if i % 500 == 0:
            print("Candidate value matches", i, flush=True)
    candidate = minutes.rename(columns={"vaep": "baseline_vaep"}).merge(
        pd.concat(totals, ignore_index=True).rename(columns={"vaep_value": "vaep"}),
        on=["game_id", "player_id"],
        how="left",
        validate="one_to_one",
    )
    candidate["vaep"] = candidate.vaep.fillna(0)
    candidate.to_parquet(out / "player_match_vaep.parquet", index=False)
    players = candidate.groupby("player_id").agg(
        name=("name", "last"),
        minutes=("minutes", "sum"),
        vaep=("vaep", "sum"),
        baseline_vaep=("baseline_vaep", "sum"),
    )
    players["vaep_per90"] = players.vaep * 90 / players.minutes
    players["baseline_per90"] = players.baseline_vaep * 90 / players.minutes
    eligible = players[players.minutes >= 900]
    baseline_top = eligible.nlargest(20, "baseline_per90")
    candidate_top = eligible.nlargest(20, "vaep_per90")
    final = pd.read_parquet(out / "vaep/3869685.parquet")
    goals = final[
        (final.period_id < 5)
        & final.type_name.str.startswith("shot")
        & (final.result_name == "success")
    ]
    result = {
        "minutes_definition": "unchanged minutes from incumbent player-match table",
        "n_players_min900": len(eligible),
        "spearman_per90": float(
            spearmanr(eligible.baseline_per90, eligible.vaep_per90).statistic
        ),
        "top20_overlap": len(set(baseline_top.index) & set(candidate_top.index)),
        "top20_per90_min900": candidate_top.reset_index().to_dict("records"),
        "final_goals": goals[
            [
                "action_id",
                "period_id",
                "vaep_value",
                "offensive_value",
                "defensive_value",
            ]
        ].to_dict("records"),
    }
    if not np.isfinite(eligible.vaep_per90).all() or (goals.vaep_value <= 0).any():
        raise ValueError("Candidate ranking/goal sanity failed")
    players.reset_index().to_parquet(out / "player_vaep_totals.parquet", index=False)
    write_report(out / "vaep_sanity.json", result)
    print(
        json.dumps({k: result[k] for k in ("spearman_per90", "top20_overlap")}),
        flush=True,
    )
    return result


def main() -> None:
    """Build promotable candidate action files and ranking evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="vaep-v1")
    args = parser.parse_args()
    run(destination(args.run))


if __name__ == "__main__":
    main()
