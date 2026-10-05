"""Pure modelled regulation outlook from verified score and shot-only history."""

from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.special import softmax

from matchpulse.backtest.inplay_poisson import exposure, result_probabilities

FEATURES = [
    "minute",
    "period",
    "score_home",
    "score_away",
    "score_diff",
    "xg_home",
    "xg_away",
    "recent_xg_home",
    "recent_xg_away",
]


def perspective(rows: pd.DataFrame, side: str) -> pd.DataFrame:
    other = "away" if side == "home" else "home"
    out = rows[["minute", "period"]].copy()
    out["is_home"] = int(side == "home")
    for feature in ["score", "xg", "recent_xg"]:
        out[f"{feature}_for"] = rows[f"{feature}_{side}"]
        out[f"{feature}_against"] = rows[f"{feature}_{other}"]
    out["score_diff"] = out.score_for - out.score_against
    return out


class LiteOutlook:
    """Serializable model; callers must supply a verified pre-minute snapshot."""

    def __init__(self, regressor: lgb.LGBMRegressor, temperature: float = 1.0) -> None:
        self.regressor = regressor
        self.temperature = temperature

    def rates(self, rows: pd.DataFrame) -> np.ndarray:
        x = rows[FEATURES].astype(float)
        if not np.isfinite(x.to_numpy()).all() or not x.period.isin([1, 2]).all():
            raise ValueError("Finite verified regulation snapshots required")
        if ((x.minute < 0) | (x.minute > 90)).any():
            raise ValueError("Unsupported anchor minute")
        self.regressor.set_params(n_jobs=1)
        return np.column_stack(
            [
                self.regressor.predict(perspective(x, s)) * exposure(x)
                for s in ["home", "away"]
            ]
        )

    def predict_proba(self, rows: pd.DataFrame) -> np.ndarray:
        rates = self.rates(rows)
        p = result_probabilities(rows.score_diff.to_numpy(), rates[:, 0], rates[:, 1])
        return softmax(np.log(np.clip(p, 1e-9, 1)) / self.temperature, axis=1)


def outlook(state: dict[str, float], model: LiteOutlook) -> dict[str, Any]:
    """Describe a modelled outlook, never a causal intervention or full-match xG."""
    row = pd.DataFrame([state])
    rates = model.rates(row)[0]
    p = model.predict_proba(row)[0]
    return {
        "modelled": True,
        "horizon": "end of regulation including added time",
        "expected_goals_remaining": dict(
            zip(["home", "away"], map(float, rates), strict=True)
        ),
        "result_probability": dict(
            zip(["home", "draw", "away"], map(float, p), strict=True)
        ),
        "limits": "Observational shot outlook; no substitution or red-card effects",
    }
