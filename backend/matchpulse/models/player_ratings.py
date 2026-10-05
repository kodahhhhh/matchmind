"""Leave-out player quality ratings: shrunk VAEP per 90 from other matches only.

A player's rating for a window never uses the window's own match. Validation
additionally drops every match in the held-out fold, so test rows see ratings
built purely from training matches. Ratings use out-of-fold VAEP values and
career-wide (not strictly prior-in-time) minutes: this is retrospective
analysis, not a forecast. Shrinkage pulls low-minute players to the corpus mean.
"""

from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache

import numpy as np
import pandas as pd

from matchpulse.models.common import catalogue, data_dir

# Minutes of corpus-average play added to every player; 900 = ten full matches.
PRIOR_MINUTES = 900.0
PATH = "processed/player_match_vaep.parquet"


def build() -> pd.DataFrame:
    """Per (player, match) playing minutes and out-of-fold VAEP."""
    with ProcessPoolExecutor(max_workers=8) as pool:
        frames = list(pool.map(_rows, catalogue()))
    result = pd.DataFrame([r for frame in frames for r in frame])
    result = result[result.minutes > 0].reset_index(drop=True)
    result.to_parquet(data_dir() / PATH, index=False)
    return result


def _rows(match: dict) -> list[dict]:
    from matchpulse.models.sanity import player_totals

    return [{**r, "game_id": match["native_id"]} for r in player_totals(match)]


@lru_cache(maxsize=1)
def table() -> pd.DataFrame:
    path = data_dir() / PATH
    return pd.read_parquet(path) if path.exists() else build()


@lru_cache(maxsize=1)
def _totals() -> tuple[pd.DataFrame, float]:
    t = table()
    totals = t.groupby("player_id")[["minutes", "vaep"]].sum()
    return totals, float(t.vaep.sum() / t.minutes.sum())


def per90(
    vaep: np.ndarray | float, minutes: np.ndarray | float, mean_rate: np.ndarray | float
) -> np.ndarray:
    """Shrunk VAEP per 90 from the remaining (non-excluded) minutes."""
    return (
        (np.asarray(vaep) + PRIOR_MINUTES * mean_rate)
        / (np.asarray(minutes) + PRIOR_MINUTES)
        * 90
    )


def ratings_lomo(player_ids: list[int], game_id: int) -> dict[int, float]:
    """Ratings excluding one match; unseen players get the corpus mean."""
    totals, mean_rate = _totals()
    own = table()
    own = own[own.game_id == game_id].set_index("player_id")
    out = {}
    for pid in player_ids:
        v = m = 0.0
        if pid in totals.index:
            v, m = totals.at[pid, "vaep"], totals.at[pid, "minutes"]
        if pid in own.index:
            v -= own.at[pid, "vaep"]
            m -= own.at[pid, "minutes"]
        out[pid] = float(per90(v, max(m, 0.0), mean_rate))
    return out


def lineup_features(windows: pd.DataFrame, exclude_fold: int | None) -> pd.DataFrame:
    """Sum on-pitch ratings for each window row, for and against.

    `windows` needs game_id plus on_pitch_for/on_pitch_against id lists.
    The row's own match is always excluded; exclude_fold also drops that
    whole fold (used to build training and test rows for fold validation).
    """
    t = table() if exclude_fold is None else outer_table(exclude_fold)
    return lineup_from_table(windows, t, exclude_own_prior=exclude_fold is not None)


@lru_cache(maxsize=1)
def outer_table(fold: int) -> pd.DataFrame:
    """Revalue training matches with VAEP models excluding this outer fold."""
    from matchpulse.models.outer_player_ratings import rebuild

    return rebuild(fold, table())


def lineup_from_table(
    windows: pd.DataFrame, t: pd.DataFrame, *, exclude_own_prior: bool = False
) -> pd.DataFrame:
    """Aggregate an explicitly supplied, already outer-safe rating table."""
    kept = t
    totals = kept.groupby("player_id")[["minutes", "vaep"]].sum()
    match_totals = kept.groupby("game_id")[["minutes", "vaep"]].sum()
    corpus = match_totals.sum()
    remaining_minutes = corpus.minutes - match_totals.minutes
    mean_rate = float(kept.vaep.sum() / kept.minutes.sum())
    prior_by_game = ((corpus.vaep - match_totals.vaep) / remaining_minutes).where(
        remaining_minutes > 0, 0.0
    )
    own = t.set_index(["player_id", "game_id"])[["minutes", "vaep"]]
    own = own[~own.index.duplicated()]
    out = pd.DataFrame(index=windows.index)
    for side in ("for", "against"):
        long = (
            windows[["game_id", f"on_pitch_{side}"]]
            .rename(columns={f"on_pitch_{side}": "player_id"})
            .explode("player_id")
            .dropna()
        )
        long["player_id"] = long.player_id.astype(np.int64)
        base = totals.reindex(long.player_id.to_numpy()).fillna(0).to_numpy()
        # Subtract the row's own match unless the fold exclusion already did.
        keys = pd.MultiIndex.from_arrays([long.player_id, long.game_id])
        mine = own.reindex(keys).fillna(0).to_numpy()
        remaining = base - mine  # columns: minutes, vaep (VAEP may be negative)
        long["rating"] = per90(
            remaining[:, 1],
            np.clip(remaining[:, 0], 0, None),
            (
                long.game_id.map(prior_by_game).fillna(mean_rate).to_numpy()
                if exclude_own_prior
                else mean_rate
            ),
        )
        out[f"lineup_vaep_{side}"] = (
            long.groupby(level=0).rating.sum().reindex(windows.index).fillna(0)
        )
    return out
