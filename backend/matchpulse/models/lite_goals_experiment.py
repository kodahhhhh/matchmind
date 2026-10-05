"""Validate shots-only outputs by degrading StatsBomb with chronological upstream."""

import argparse
import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import softmax

from matchpulse.backtest.inplay_poisson import PARAMS, exposure, regulation_goals
from matchpulse.models.common import catalogue, data_dir, timestamp
from matchpulse.models.evaluate import (
    bundle_predict,
    destination,
    inplay_data,
    write_report,
)
from matchpulse.models.evaluation import compare, file_hash, freeze_manifest, losses
from matchpulse.models.lite import chance_summary, snapshot
from matchpulse.models.lite_goals import LiteOutlook, perspective
from matchpulse.models.xg_shot import statsbomb_features


def audit_upstream(out: Path) -> dict:
    """Give the matched historical shot artifact its own validation sidecar."""
    from matchpulse.models.xg import FEATURES as FULL_FEATURES

    root = data_dir()
    protocol = json.loads((out / "protocol.json").read_text())
    shots = pd.read_parquet(root / "processed/xg/shots.parquet")
    historical = shots.game_id.isin(protocol["upstream_match_ids"])
    ids = pd.read_parquet(
        out / "snapshots.parquet", columns=["game_id"]
    ).game_id.unique()
    rows = shots[shots.game_id.isin(ids) & (shots.period < 3)]
    full = lgb.Booster(model_file=str(root / "models/backtest_prematch_xg.txt"))
    reduced = lgb.Booster(model_file=str(out / "xg_shot_historical.txt"))
    report = {
        "training_date": timestamp(),
        "n_matches": len(protocol["upstream_match_ids"]),
        "n_shots": int((historical & (shots.period < 3)).sum()),
        "training_cutoff": "2015-08-01",
        "validation": "regulation shots in disjoint result-model matches",
        "baseline_definition": "original pre-2015 full-context upstream artifact",
        **compare(
            rows.goal.to_numpy(),
            full.predict(rows[FULL_FEATURES], num_threads=8),
            reduced.predict(statsbomb_features(rows), num_threads=8),
            rows.game_id.to_numpy(),
        ),
        "promotion_recommended": False,
        "role": "matched upstream for held lite-goals-v1 prototype only",
    }
    write_report(out / "xg_shot_historical.json", report)
    return report


def run(out: Path) -> dict:
    root = data_dir()
    data = inplay_data(out)
    shot_path = root / "processed/xg/shots.parquet"
    matches = {m["native_id"]: m for m in catalogue()}
    historical = {
        g
        for g, m in matches.items()
        if m["match_date"] and m["match_date"] < "2015-08-01"
    }
    fresh_path = root / "models/candidates/inplay-poisson-v1/fresh_features.parquet"
    fresh = pd.read_parquet(fresh_path)
    data = pd.concat([data, fresh], ignore_index=True)
    paths = [shot_path, fresh_path, root / "models/backtest_inplay.joblib"]
    paths += [
        root / f"processed/spadl/{g}.parquet" for g in sorted(data.game_id.unique())
    ]
    paths += [
        root / f"raw/statsbomb/data/events/{g}.json"
        for g in sorted(data.game_id.unique())
    ]
    freeze_manifest(
        out / "protocol.json",
        {
            "protocol": "fixed Poisson recipe; chronological shot-only degradation",
            "inputs": {str(p.relative_to(root)): file_hash(p) for p in paths},
            "upstream_match_ids": sorted(historical),
            "upstream_cutoff": "2015-08-01",
            "fit": "original pre-2018 result partition",
            "calibration": "2018-2019",
            "test": (
                "previously reported test cohorts; prototype diagnostic; no selection"
            ),
            "params": PARAMS,
        },
    )
    if (out / "lite_goals.json").exists():
        raise ValueError("Completed candidate exists")
    shots = pd.read_parquet(shot_path)
    shots = shots[shots.period < 3].copy()
    x = statsbomb_features(shots)
    mask = shots.game_id.isin(historical)
    upstream = lgb.LGBMClassifier(
        n_estimators=200,
        learning_rate=0.035,
        num_leaves=15,
        min_child_samples=100,
        reg_lambda=5,
        n_jobs=8,
        verbosity=-1,
        random_state=2026,
    ).fit(
        x[mask], shots.loc[mask, "goal"], categorical_feature=["body_part", "situation"]
    )
    upstream.booster_.save_model(str(out / "xg_shot_historical.txt"))
    shots["xg"] = upstream.predict_proba(x)[:, 1]
    source = data.copy()
    grouped = dict(tuple(shots.groupby("game_id")))
    summaries = []
    for i, (game, rows) in enumerate(source.groupby("game_id")):
        actions = pd.read_parquet(root / f"processed/spadl/{game}.parquet")
        actions = actions[
            actions.type_name.str.startswith("shot") & (actions.period_id < 3)
        ]
        s = grouped[game].merge(
            actions[["original_event_id", "team_id"]],
            on="original_event_id",
            validate="one_to_one",
        )
        s["team"] = np.where(s.team_id == matches[game]["home"]["id"], "home", "away")
        s["id"] = s.original_event_id
        s["second"] = None
        summary = chance_summary(s)
        # Pure aggregate sums must equal the independent grouped shot reductions.
        for side in ["home", "away"]:
            if not np.isclose(
                summary["teams"][side]["xg"], s.loc[s.team == side, "xg"].sum()
            ):
                raise ValueError("Lite aggregate mismatch")
        summaries.append(
            {
                "game_id": game,
                **{
                    f"xg_{side}": summary["teams"][side]["xg"]
                    for side in ["home", "away"]
                },
            }
        )
        anchor_period = rows.period.to_numpy()[:, None]
        anchor_minute = rows.minute.to_numpy()[:, None]
        shot_period = s.period.to_numpy()[None, :]
        shot_minute = s.minute.to_numpy()[None, :]
        past = (shot_period < anchor_period) | (
            (shot_period == anchor_period) & (shot_minute < anchor_minute)
        )
        recent = (
            past & (shot_period == anchor_period) & (shot_minute >= anchor_minute - 5)
        )
        for side in ["home", "away"]:
            weights = (s.xg * (s.team == side)).to_numpy()
            source.loc[rows.index, f"xg_{side}"] = past @ weights
            source.loc[rows.index, f"recent_xg_{side}"] = recent @ weights / 5
        anchor = rows.iloc[-1]
        checked = snapshot(
            s,
            period=int(anchor.period),
            minute=int(anchor.minute),
            score={"home": int(anchor.score_home), "away": int(anchor.score_away)},
        )
        if not np.allclose(
            source.loc[rows.index[-1], list(checked)].astype(float),
            list(checked.values()),
        ):
            raise ValueError("Batch snapshot differs from pure public snapshot")
        events = json.loads(
            (root / f"raw/statsbomb/data/events/{game}.json").read_text()
        )
        h, a = regulation_goals(matches[game], events)
        source.loc[rows.index, "remaining_home"] = h - rows.score_home
        source.loc[rows.index, "remaining_away"] = a - rows.score_away
        if i % 500 == 0:
            print("Degraded matches", i, flush=True)
    source.to_parquet(out / "snapshots.parquet", index=False)
    pd.DataFrame(summaries).to_parquet(out / "summary_validation.parquet", index=False)
    train = source[source.split == "train"]
    e = exposure(train)
    fit_x = pd.concat(
        [perspective(train, s) for s in ["home", "away"]], ignore_index=True
    )
    fit_y = np.concatenate(
        [train[f"remaining_{s}"].to_numpy() / e for s in ["home", "away"]]
    )
    regressor = lgb.LGBMRegressor(**PARAMS).fit(
        fit_x, fit_y, sample_weight=np.tile(e, 2)
    )
    model = LiteOutlook(regressor)
    cal = source[source.split == "calibration"]
    logits = np.log(np.clip(model.predict_proba(cal), 1e-9, 1))
    fit = minimize_scalar(
        lambda t: losses(cal.result.to_numpy(), softmax(logits / t, axis=1))[
            "log_loss"
        ].mean(),
        bounds=(0.5, 3),
        method="bounded",
    )
    if not fit.success:
        raise ValueError("Calibration failed")
    model.temperature = float(fit.x)
    joblib.dump(model, out / "lite_goals.joblib")
    model = joblib.load(out / "lite_goals.joblib")
    incumbent = joblib.load(root / "models/backtest_inplay.joblib")
    result = {}
    for name in ["validation", "backtest", "excluded"]:
        selected = source.split == name
        rows = source[selected]
        p = bundle_predict(incumbent, data[selected])
        naive = bundle_predict(incumbent, data[selected], "baseline")
        q = model.predict_proba(rows)
        result[name] = {
            **compare(rows.result.to_numpy(), p, q, rows.game_id.to_numpy()),
            "vs_naive": compare(
                rows.result.to_numpy(), naive, q, rows.game_id.to_numpy()
            ),
            "n_matches": int(rows.game_id.nunique()),
        }
    card = {
        "training_date": timestamp(),
        "n_matches": int(train.game_id.nunique()),
        "n_rows": len(train),
        "params": PARAMS,
        "temperature": model.temperature,
        **result["validation"],
        "cohorts": result,
        "summary_matches_verified": len(summaries),
        "validation": (
            "chronological upstream; pre-minute degradation; diagnostic test cohorts"
        ),
        "promotion_recommended": False,
        "requires": "verified periods and score; unavailable on current Understat",
    }
    write_report(out / "lite_goals.json", card)
    audit_upstream(out)
    print(json.dumps({"paired_ci": card["paired_ci"]}, indent=2), flush=True)
    return card


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="lite-goals-v1")
    run(destination(parser.parse_args().run))


if __name__ == "__main__":
    main()
