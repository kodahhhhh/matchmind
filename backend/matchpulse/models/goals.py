"""Goal-rate models and final-result probabilities for what-if questions.

Two LightGBM Poisson regressions on the game-state windows, team perspective:
- goals_next15: goals the team scores in the next 15 playing minutes;
- goals_rest:   goals the team scores before the end of the current block
  (90 minutes plus stoppage, or the end of extra time).
Targets are actual goals (own goals credited to the beneficiary), not xG.

Result probabilities treat each side's remaining goals as independent Poisson
with that side's own predicted rate, added to the current score. A draw at the
end of normal time means extra time in a knockout match; a draw after extra
time means penalties.

Validation uses the same outer match folds as the game-state model, with the
fold-rebuilt windows (upstream xG/VAEP and player ratings exclude the held-out
fold). Like everything here, it is observational: it describes what usually
happened next in similar states, not a causal effect.
"""

import json
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import poisson

from matchpulse.models.common import (
    catalogue,
    data_dir,
    event_clock,
    event_seconds,
    fold_map,
    raw_events,
    save_json,
    timestamp,
)
from matchpulse.models.gamestate_model import FEATURES as STATE_FEATURES

TARGETS = ["goals_next15", "goals_rest"]
FEATURES = STATE_FEATURES + ["block_minutes_left", "is_extra_time"]
BASELINE = ["minute", "score_diff", "block_minutes_left", "is_extra_time", "is_home"]
LEAGUE_STAGES = {"Regular Season", "Group Stage", "1st Group Stage", "Apertura", None}
PARAMS = dict(
    objective="poisson",
    n_estimators=250,
    learning_rate=0.03,
    num_leaves=15,
    min_child_samples=300,
    reg_lambda=5,
    n_jobs=16,
    verbosity=-1,
    random_state=2026,
)
MAX_GOALS = 12


def knockout(match: dict) -> bool:
    return match.get("stage") not in LEAGUE_STAGES


def match_goals(match: dict[str, Any]) -> dict[str, Any]:
    """Goal times (playing clock) per team id, plus block end times."""
    events = [e for e in raw_events(match["native_id"]) if e["period"] < 5]
    offsets, lengths = event_clock(events)
    home, away = match["home"]["id"], match["away"]["id"]
    goals = []
    for event in events:
        team = event["team"]["id"]
        t = offsets[event["period"]] + event_seconds(event)
        kind = event["type"]["name"]
        if kind == "Shot" and event["shot"]["outcome"]["name"] == "Goal":
            goals.append((t, team))
        elif kind == "Own Goal Against":
            goals.append((t, away if team == home else home))
    regulation = offsets[2] + lengths[2] if 2 in lengths else max(offsets.values())
    last = max(lengths)
    extra = offsets[last] + lengths[last]
    return {"goals": goals, "regulation_end": regulation, "extra_end": extra}


def window_targets(match: dict[str, Any]) -> pd.DataFrame:
    info = match_goals(match)
    return pd.DataFrame(
        [
            {
                "game_id": match["native_id"],
                "team_id": tid,
                "t": t,
            }
            for t, tid in info["goals"]
        ]
        or [{"game_id": match["native_id"], "team_id": -1, "t": -1.0}]
    ).assign(
        regulation_end=info["regulation_end"],
        extra_end=info["extra_end"],
        knockout=knockout(match),
    )


def add_targets(windows: pd.DataFrame) -> pd.DataFrame:
    """Attach goal targets and block features to window rows (team perspective)."""
    matches = {m["native_id"]: m for m in catalogue()}
    with ProcessPoolExecutor(max_workers=16) as pool:
        tables = list(pool.map(window_targets, matches.values()))
    goals = pd.concat(tables, ignore_index=True)
    blocks = goals.groupby("game_id")[
        ["regulation_end", "extra_end", "knockout"]
    ].first()
    w = windows.join(blocks, on="game_id")
    team_id = np.where(
        w.team == "home",
        w.game_id.map(lambda g: matches[g]["home"]["id"]),
        w.game_id.map(lambda g: matches[g]["away"]["id"]),
    )
    end = w.elapsed_end_seconds.to_numpy()
    in_extra = w.period.to_numpy() >= 3
    block_end = np.where(in_extra, w.extra_end, w.regulation_end)
    by_game = {g: f for g, f in goals[goals.team_id >= 0].groupby("game_id")}
    next_for, next_against, rest_for, rest_against = (np.zeros(len(w)) for _ in "abcd")
    for i, (g, tid, e, be) in enumerate(
        zip(w.game_id, team_id, end, block_end, strict=True)
    ):
        f = by_game.get(g)
        if f is None:
            continue
        mine = (f.team_id == tid).to_numpy()
        t = f.t.to_numpy()
        nxt = (t >= e) & (t < e + 900)
        rest = (t >= e) & (t < be)
        next_for[i], next_against[i] = (nxt & mine).sum(), (nxt & ~mine).sum()
        rest_for[i], rest_against[i] = (rest & mine).sum(), (rest & ~mine).sum()
    nominal_end = np.where(in_extra, 120.0, 90.0)
    return w.assign(
        goals_next15=next_for,
        goals_next15_against=next_against,
        goals_rest=rest_for,
        goals_rest_against=rest_against,
        block_minutes_left=np.clip(nominal_end - w.minute.to_numpy(), 0, None),
        is_extra_time=in_extra.astype(float),
    )


def block_features(minute: float, period: int) -> dict[str, float]:
    """Inference-time block features from the anchor's nominal minute."""
    extra = period >= 3
    return {
        "block_minutes_left": max((120.0 if extra else 90.0) - minute, 0.0),
        "is_extra_time": float(extra),
    }


def outcome_probs(
    lam_home: np.ndarray, lam_away: np.ndarray, diff: np.ndarray
) -> np.ndarray:
    """P(home ahead, level, away ahead) at block end, given current home-away diff."""
    k = np.arange(MAX_GOALS + 1)
    ph = poisson.pmf(k[None, :], lam_home[:, None])
    pa = poisson.pmf(k[None, :], lam_away[:, None])
    joint = ph[:, :, None] * pa[:, None, :]
    margin = diff[:, None, None] + k[None, :, None] - k[None, None, :]
    return np.stack(
        [
            (joint * (margin > 0)).sum((1, 2)),
            (joint * (margin == 0)).sum((1, 2)),
            (joint * (margin < 0)).sum((1, 2)),
        ],
        axis=1,
    )


def train() -> None:
    from matchpulse.models.windows import load_or_build

    folds_of = fold_map()
    production = add_targets(load_or_build())
    report: dict[str, Any] = {
        "training_date": timestamp(),
        "features": FEATURES,
        "baseline_features": BASELINE,
        "params": PARAMS,
        "validation": (
            "5 grouped outer match folds on fold-rebuilt windows (upstream xG/VAEP "
            "and player ratings exclude the held-out fold). Targets are actual goals."
        ),
        "metrics": {},
    }
    oof = {t: np.zeros(len(production)) for t in TARGETS}
    base = {t: np.zeros(len(production)) for t in TARGETS}
    score_effect = []
    folds = production.game_id.map(folds_of).to_numpy()
    for fold in range(5):
        nested = add_targets(load_or_build(fold))
        assert nested[["game_id", "team", "elapsed_end_seconds"]].equals(
            production[["game_id", "team", "elapsed_end_seconds"]]
        )
        test = folds == fold
        x = nested[FEATURES].astype(float)
        for target in TARGETS:
            # next-15 needs a complete horizon; rest-of-block is always observed
            ok = (
                (nested.horizon_seconds >= 900).to_numpy()
                if target == "goals_next15"
                else np.ones(len(nested), bool)
            )
            y = nested[target].to_numpy()
            model = lgb.LGBMRegressor(**PARAMS).fit(x[~test & ok], y[~test & ok])
            oof[target][test] = model.predict(x[test])
            simple = lgb.LGBMRegressor(**PARAMS).fit(
                x.loc[~test & ok, BASELINE], y[~test & ok]
            )
            base[target][test] = simple.predict(x.loc[test, BASELINE])
            if target == "goals_next15":
                lead, trail = x[test].copy(), x[test].copy()
                lead["score_diff"], trail["score_diff"] = 1, -1
                score_effect.append(
                    (model.predict(trail).mean(), model.predict(lead).mean())
                )
        print("Goals fold", fold, flush=True)

    def deviance(y: np.ndarray, mu: np.ndarray) -> float:
        mu = np.clip(mu, 1e-9, None)
        term = np.where(y > 0, y * np.log(np.where(y > 0, y, 1) / mu), 0.0)
        return float(2 * np.mean(term - (y - mu)))

    for target in TARGETS:
        ok = (
            (production.horizon_seconds >= 900).to_numpy()
            if target == "goals_next15"
            else np.ones(len(production), bool)
        )
        y = production[target].to_numpy()[ok]
        const = np.zeros(ok.sum())
        for fold in range(5):
            sel = folds[ok] == fold
            const[sel] = y[~sel].mean()
        report["metrics"][target] = {
            "n": int(ok.sum()),
            "mean_goals": float(y.mean()),
            "poisson_deviance": {
                "model": deviance(y, oof[target][ok]),
                "score_and_clock": deviance(y, base[target][ok]),
                "constant": deviance(y, const),
            },
            "mean_predicted": float(oof[target][ok].mean()),
        }
        if target == "goals_next15":
            scored = (y > 0).astype(float)
            p = 1 - np.exp(-oof[target][ok])
            pb = 1 - np.exp(-base[target][ok])
            report["metrics"][target]["p_score_brier"] = {
                "model": float(np.mean((p - scored) ** 2)),
                "score_and_clock": float(np.mean((pb - scored) ** 2)),
                "constant": float(np.mean((scored.mean() - scored) ** 2)),
            }
            bins = pd.qcut(p, 10, labels=False, duplicates="drop")
            report["metrics"][target]["p_score_calibration"] = [
                {
                    "predicted": float(p[bins == b].mean()),
                    "observed": float(scored[bins == b].mean()),
                }
                for b in sorted(set(bins))
            ]

    # Block result (home ahead / level / away ahead at block end), per window.
    pr = production.assign(rate=oof["goals_rest"], base=base["goals_rest"])
    home = pr[pr.team == "home"].set_index(["game_id", "elapsed_end_seconds"])
    away = (
        pr[pr.team == "away"]
        .set_index(["game_id", "elapsed_end_seconds"])
        .reindex(home.index)
    )
    final_diff = (
        home.score_diff + home.goals_rest - home.goals_rest_against
    ).to_numpy()
    actual = np.stack([final_diff > 0, final_diff == 0, final_diff < 0], axis=1).astype(
        float
    )
    diff = home.score_diff.to_numpy().astype(float)
    result = {}
    for name, col in (("model", "rate"), ("score_and_clock", "base")):
        probs = outcome_probs(home[col].to_numpy(), away[col].to_numpy(), diff)
        result[name] = {
            "brier": float(((probs - actual) ** 2).sum(1).mean()),
            "log_loss": float(
                -np.log(np.clip((probs * actual).sum(1), 1e-12, None)).mean()
            ),
        }
    # Naive: the current score stands.
    naive = (
        np.stack([diff > 0, diff == 0, diff < 0], axis=1).astype(float) * 0.9 + 0.1 / 3
    )
    result["score_stands"] = {
        "brier": float(((naive - actual) ** 2).sum(1).mean()),
        "log_loss": float(-np.log((naive * actual).sum(1)).mean()),
    }
    report["metrics"]["block_result"] = {"n": int(len(home)), **result}
    trail, lead = (
        np.mean([a for a, _ in score_effect]),
        np.mean([b for _, b in score_effect]),
    )
    report["score_effect"] = {
        "definition": (
            "Mean predicted next-15 goals for held-out rows with score_diff set "
            "to -1 versus +1, everything else fixed (observational, not causal)."
        ),
        "trailing": float(trail),
        "leading": float(lead),
    }
    x = production[FEATURES].astype(float)
    for target in TARGETS:
        ok = (
            (production.horizon_seconds >= 900).to_numpy()
            if target == "goals_next15"
            else np.ones(len(production), bool)
        )
        model = lgb.LGBMRegressor(**PARAMS).fit(x[ok], production[target][ok])
        model.booster_.save_model(str(data_dir() / f"models/goals_{target}.txt"))
    report["n_windows"] = int(len(production))
    report["n_matches"] = int(production.game_id.nunique())
    save_json("goals.json", report)
    print(json.dumps(report["metrics"], indent=1), json.dumps(report["score_effect"]))


@lru_cache(maxsize=2)
def _model(target: str) -> lgb.Booster:
    return lgb.Booster(model_file=str(data_dir() / f"models/goals_{target}.txt"))


@lru_cache(maxsize=1)
def report() -> dict:
    return json.loads((data_dir() / "models/goals.json").read_text())


def rates(features: pd.DataFrame, target: str) -> np.ndarray:
    """Expected goals (actual-goal rate) per row, team perspective."""
    return _model(target).predict(features[FEATURES].astype(float), num_threads=1)


if __name__ == "__main__":
    train()


def outlook(
    factual: pd.DataFrame,
    changed: pd.DataFrame,
    period: int,
    score: dict[str, int],
    changed_score: dict[str, int],
    is_knockout: bool,
) -> dict[str, Any]:
    """Result and next-15 scoring chances, real state versus changed state.

    `factual`/`changed` are home-then-away game-state feature rows at the anchor.
    """

    def run(rows: pd.DataFrame, current: dict[str, int]) -> tuple[dict, dict]:
        frame = rows.assign(**block_features(float(rows.minute.iloc[0]), period))
        rest = rates(frame, "goals_rest")
        nxt = rates(frame, "goals_next15")
        probs = outcome_probs(
            rest[:1], rest[1:], np.array([current["home"] - current["away"]], float)
        )[0]
        chance = 1 - np.exp(-nxt)
        return (
            {
                k: round(float(v), 4)
                for k, v in zip(("home", "level", "away"), probs, strict=True)
            },
            {"home": round(float(chance[0]), 4), "away": round(float(chance[1]), 4)},
        )

    real_result, real_chance = run(factual, score)
    new_result, new_chance = run(changed, changed_score)
    extra = period >= 3
    return {
        "result": {
            "block": "extra_time" if extra else "normal_time",
            "level_means": "penalties"
            if extra
            else ("extra_time" if is_knockout else "draw"),
            "score": {"factual": score, "modelled": changed_score},
            "factual": real_result,
            "modelled": new_result,
        },
        "scoring_chance": {"factual": real_chance, "modelled": new_chance},
    }
