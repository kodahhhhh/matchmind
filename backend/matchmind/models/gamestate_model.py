"""Quantile forecasts of the next 15 playing minutes, in team perspective.

featurize accepts flat window rows or rows with a nested `features` dictionary.
FEATURES is the exact ordered inference contract. Past-window sums cover five
minutes; possession is pass-count share (all pass actions),
field tilt is the share of actions starting in the attacking third. Both are
fractions. xT rates are successful-move value per minute. Substitution ages
and minute are minutes; xG/VAEP are window sums.

predict returns target -> {p10, p50, p90}, each a list aligned with input rows.
All forecasts/counterfactuals must be labelled MODELLED. To form a hypothetical,
copy the feature row and change just the intervention: remove_goal subtracts
one from score_diff for the scoring side (adds one for its opponent); no_sub
resets minutes_since_sub to its pre-substitution age, or elapsed match minutes
if no prior substitution; remove_red_card restores the affected players count
(up to 11). Do not blindly restore both teams if only one card is removed.
Re-predict the copy. This is an observational sensitivity calculation, NOT a
causal estimate: goals, substitutions and dismissals are not randomized.
"""

from functools import lru_cache
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from matchmind.models.common import data_dir

FEATURES = [
    "minute",
    "period",
    "score_diff",
    "possession_share",
    "field_tilt",
    "xg_for",
    "xg_against",
    "vaep_for",
    "vaep_against",
    "xt_for_rate",
    "xt_against_rate",
    "shots_for",
    "shots_against",
    "minutes_since_sub",
    "minutes_since_opponent_sub",
    "players_for",
    "players_against",
    "is_home",
    "international_tournament",
]
TARGETS = ["xg_for", "xg_against", "possession_share"]
QUANTILES = [0.1, 0.5, 0.9]


def featurize(window_rows: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    """Select exact FEATURES, reject missing/nonfinite columns and preserve order."""
    frame = pd.DataFrame(window_rows).copy()
    if "features" in frame:
        frame = pd.DataFrame(frame.features.tolist(), index=frame.index)
    missing = set(FEATURES) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing game-state features: {sorted(missing)}")
    result = frame[FEATURES].astype(float)
    if not np.isfinite(result.to_numpy()).all():
        raise ValueError("Game-state features must be finite")
    return result


@lru_cache(maxsize=9)
def _model(target: str, quantile: int) -> lgb.Booster:
    return lgb.Booster(
        model_file=str(data_dir() / f"models/gamestate_{target}_p{quantile}.txt")
    )


def bound_predictions(values: np.ndarray, target: str) -> np.ndarray:
    """Rearrange crossing quantiles and enforce each target's physical support."""
    return np.sort(
        np.clip(values, 0, 1 if target == "possession_share" else np.inf), axis=1
    )


def predict(features: pd.DataFrame) -> dict[str, dict[str, list[float]]]:
    frame = featurize(features)
    result = {}
    for target in TARGETS:
        values = bound_predictions(
            np.column_stack(
                [_model(target, q).predict(frame, num_threads=1) for q in [10, 50, 90]]
            ),
            target,
        )
        result[target] = {
            f"p{q}": values[:, i].tolist() for i, q in enumerate([10, 50, 90])
        }
    return result
