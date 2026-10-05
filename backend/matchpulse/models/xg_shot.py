"""Own shot-only xG: pure feature/inference interface for lite loaders.

Coordinates are attacking-team +x, 105 x 68 metres. No endpoint, outcome,
provider xG, inferred clock/score or unobserved event context enters features.
"""

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

FEATURES = ["x", "y_offset", "distance", "angle", "body_part", "situation"]
BODY = {
    "Left Foot": 0,
    "Right Foot": 0,
    "LeftFoot": 0,
    "RightFoot": 0,
    "Head": 1,
    "Header": 1,
    "Other": 2,
    "OtherBodyPart": 2,
}
SITUATION = {
    "Open Play": 0,
    "OpenPlay": 0,
    "RegularPlay": 0,
    "FastBreak": 0,
    "SetPiece": 1,
    "FromCorner": 1,
    "Corner": 1,
    "FromSetPiece": 1,
    "Free Kick": 2,
    "DirectFreekick": 2,
    "FreeKick": 2,
    "Penalty": 3,
}


def features(shots: pd.DataFrame) -> pd.DataFrame:
    """Build features from shot starts; unknown categories remain missing."""
    if not {"x", "y", "body_part", "situation"}.issubset(shots.columns):
        raise ValueError("Shots need x, y, body_part and situation")
    x, y = shots.x.to_numpy(dtype=float), shots.y.to_numpy(dtype=float)
    if (
        not np.isfinite([x, y]).all()
        or ((x < 0) | (x > 105)).any()
        or ((y < 0) | (y > 68)).any()
    ):
        raise ValueError(
            "Shot starts must be finite attacking-frame metres within 105x68"
        )
    dx, dy = 105 - x, 34 - y
    return pd.DataFrame(
        {
            "x": x,
            "y_offset": abs(dy),
            "distance": np.hypot(dx, dy),
            "angle": np.arctan2(7.32 * dx, dx * dx + dy * dy - (7.32 / 2) ** 2),
            "body_part": shots.body_part.map(BODY).to_numpy(dtype=float),
            "situation": shots.situation.map(SITUATION).to_numpy(dtype=float),
        },
        index=shots.index,
    )[FEATURES]


def statsbomb_features(shots: pd.DataFrame) -> pd.DataFrame:
    """Reduce the existing pre-shot cache without inferring unavailable context."""
    out = shots[["x", "y_offset", "distance", "angle"]].copy()
    out["body_part"] = shots.body_part.map({0: 0, 1: 0, 2: 1, 3: 2})
    out["situation"] = np.select(
        [
            shots.shot_type == 3,
            shots.shot_type == 1,
            (shots.shot_type == 2) | (shots.set_piece == 1),
            shots.shot_type == 0,
        ],
        [3.0, 2.0, 1.0, 0.0],
        default=np.nan,
    )
    return out[FEATURES]


def predict(shots: pd.DataFrame, model: lgb.Booster | Path) -> pd.Series:
    """Return own xG; own-goal and shootout rows receive NaN, never zero xG."""
    if isinstance(model, Path):
        model = lgb.Booster(model_file=str(model))
    if model.feature_name() != FEATURES:
        raise ValueError("Incompatible xg_shot artifact")
    eligible = pd.Series(True, index=shots.index)
    if "result" in shots:
        eligible &= ~shots.result.isin(["OwnGoal", "Own Goal Against", "Own Goal For"])
    if "is_own_goal" in shots:
        eligible &= ~shots.is_own_goal.fillna(False).astype(bool)
    if "period" in shots:
        eligible &= shots.period.isna() | (shots.period < 5)
    p = pd.Series(np.nan, index=shots.index, name="xg", dtype=float)
    if eligible.any():
        p.loc[eligible] = model.predict(features(shots.loc[eligible]), num_threads=1)
    return p
