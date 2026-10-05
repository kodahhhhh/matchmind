# Model integration for W4 / orchestrator

The trained forecast lives in `gamestate_model.py`; `gamestate.py` remains W4's
analog implementation. Install `uv sync --group models` in the merged checkout.
Always point `DATA_DIR` at `/home/ubuntu/hackathon/data` on this host.

## Inference

```python
from matchpulse.models.gamestate_model import featurize, predict

bands = predict(featurize([feature_row]))
# bands["xg_for"]["p10"][0], bands["xg_for"]["p50"][0], ...
# Targets: xg_for, xg_against, possession_share.
```

`FEATURES` is the authoritative ordered list (19 columns). The outputs describe
the total next 15 playing minutes, not a minute-by-minute forecast path. Do not
fabricate intermediate model predictions by treating these as per-minute bands.
All counterfactual output is **modelled** and observational, not causal.

The current analog state schema is not directly interchangeable:

| Analog field | Forecast field / requirement |
| --- | --- |
| `possession` | `possession_share`; all SPADL pass types count |
| `xg_for_rate`, `xg_against_rate` | Multiply by 5 for `xg_for`, `xg_against` |
| `vaep_for_rate`, `vaep_against_rate` | Multiply by 5 for `vaep_for`, `vaep_against` |
| `xt_for_rate`, `xt_against_rate` | Same units; no positive-VAEP substitution for missing xT |
| `opponent_minutes_since_sub` | `minutes_since_opponent_sub` |
| `players_on_pitch` | `players_for` |
| `opponent_players_on_pitch` | `players_against` |
| `minute`, `period`, `score_diff`, `minutes_since_sub`, shots | Same units |
| missing | `is_home` and `international_tournament` from match metadata |
| `field_tilt` | Recompute using **start** x >70 in acting-team frame across all SPADL actions, not selected end locations |

Renaming alone is insufficient: model windows use complete SPADL (including
synthetic dribbles), period-local five-minute histories, and actual period lengths
to concatenate playing time. Current raw-event analogs can have different event
counts, boundaries and coordinate definitions. Prefer the saved window rows for
window-aligned inference/analogs. For arbitrary event anchors, reproduce the same
SPADL feature aggregation and include the anchor action before applying the
intervention (the saved fixed-boundary histories are [end-300, end)).

`remove_goal`: subtract one from score difference for the scorer's perspective;
add one for the opponent's. `no_sub`: restore the prior substitution age, or
elapsed playing minutes if there was no prior sub. `remove_red_card`: restore
one player on the affected side, at most 11. Change a copy, retain factual state.

## Historical analogs

`data/processed/gamestate_windows.parquet` includes both perspectives of all 2,924
training matches, including matches outside the 493-match demo DB. Fields include
`match_id`, `game_id`, `team`, `window_start`, `window_end`, `period`,
`elapsed_end_seconds`, `horizon_seconds`, all `FEATURES`, `outcome_xg_for`,
`outcome_xg_against`, `outcome_possession_share`, `future_passes`, competition,
season, home/away names, date, and reconstructed flag. Some dates are null.

Only use `horizon_seconds >= 900` and `future_passes > 0` when presenting complete
15-minute analog outcomes. The parquet's outcome values are already OOF. The
`gamestate_windows_fold_*` files are evaluation intermediates, not the analog
corpus. The evaluation `gamestate_oof.parquet` also uses an outer-held-out stack.

The current DB embedding has 16 dimensions; do not directly insert the 19-feature
model vector into it. Choose and version a 16-feature analog representation,
standardize it once on the corpus, and apply that same mapping to query vectors.
The all-corpus parquet includes xT rates to support the existing representation.
Its non-demo matches have metadata but no event replay in the demo DB.

## Event values

Run `uv run --group models python -m matchpulse.models.backfill` after raw reloads,
or add `--match-id sb:3869685`. This fills xG, VAEP, offensive/defensive VAEP and
xT by raw UUID and leaves genuine non-actions null. It does not replace raw rows,
change the API process, or refresh W4's sequence danger / analog tables.
Then run `uv run python -m matchpulse.db.load refresh`, and rebuild W4's downstream
sequence/ranking/analog artifacts as needed. Shootout values are available, but
period 5 must remain excluded from normal timeline and player aggregation.

## W14 round 2: shot-only xG and lite summaries

New `models.xg_shot` is independent of the full-context xG artifact. For W13's
normalized Understat/FotMob shots:

```python
from pathlib import Path
import pandas as pd
from matchpulse.models.xg_shot import predict
from matchpulse.models.lite import chance_summary

shots = pd.DataFrame(bundle["shots"])
p = predict(shots, Path(DATA_DIR) / "models/candidates/xg-shot-v1/xg_shot.txt")
shots["xg"] = p
for row, value in zip(bundle["shots"], p, strict=True):
    row["xg"] = float(value) if pd.notna(value) else None
summary = chance_summary(shots)
```

Loader requirements: attacking-team +x coordinates, 105×68 metres; `body_part`
and `situation` strings; preserve evidence `id`, team home/away, minute, nullable
period/second, result, and provider_xg separately. Do not rotate away shots into
the display frame before inference. Lateral mirroring has no effect because the
features use distance to the pitch centre line. Result, endpoint, on-target flag,
provider xG, exact score and unavailable assists are **not** features. Unknown
categories remain missing; monitor missing counts. Own goals and shootouts get
null xG, not zero; FotMob must pass `is_own_goal` from raw `isOwnGoal`.

Validated snapshot: 2,002 Understat matches / 51,086 genuine shots. Own model
Brier 0.081345 versus legacy missing-context full-model Brier 0.233350; the current
adapter was freshly replayed with zero difference from staged values. The model
is recommended for **Understat lite only**, never a replacement for full-context
StatsBomb xG. Only one FotMob sample is available; broader FotMob transfer remains
unverified. Both predictions and all source comparisons live in the candidate.

`chance_summary` returns own-xG totals, evidence IDs, minute buckets and
`home_chance_share` (fraction of total shot xG). It is **chance share**, not ball
possession, field tilt, VAEP momentum or proof of who controlled play. No shots
or zero total xG gives a null share. Unknown xG annotations are counted explicitly.
There are no invented passes, carries, sequences, actions or player-impact values.

`lite.snapshot(shots, period=..., minute=..., score={"home": ..., "away": ...})`
forms strict pre-minute shot history for a modelled outlook. It requires verified
shot periods and an independently verified anchor score. All shots in the current
minute are excluded. Understat currently has unknown periods, so **outlook is
unavailable** there; never guess periods from minutes around halftime. Final totals
and labelled minute buckets remain supported. Live exact replay and substitution,
red-card or pass-option counterfactuals are not provided by this lite interface.

These are pure model interfaces, not changes to API response schemas. W13/API owns
capability dispatch, conversion of NaN to null, fixture/schema changes and staged
backfill of lite payloads. Preserve provider metrics under provider names.
