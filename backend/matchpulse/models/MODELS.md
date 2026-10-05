# MatchPulse custom models

Measured training run: 2026-10-03T22:52:31.690662+00:00. CPU only. StatsBomb open-data source commit `4b73468`; catalogue, not the incomplete source match index, selects the corpus.

## Data, reproducibility and validation

2,924 men’s matches; 5,962,767 SPADL actions; 0 conversion failures. The 493 demo matches are a subset of training, and all corpus xG, VAEP and xT outputs are held out by match. Synthetic SPADL dribbles have no raw UUID and are excluded from the DB join. Split interception/pass actions are summed back to one raw UUID. Stored SPADL has home attacking +x; spatial training rotates each acting team to +x. DB raw coordinates are unchanged.

Five deterministic shuffled match folds (seed 2026) are shared across models. No action-level random split. Shootouts receive held-out xG/VAEP predictions for event completeness, but are excluded from training, evaluation, rankings, windows and timeline sums. Finals below exclude shootouts. All artifacts remain gitignored. Final models fit all eligible training matches; match artifacts use held-out models.

The `models` dependency group pins socceraction 1.5.3 and multimethod <2 for its pandera compatibility. Python 3.12, pandas 2, LightGBM 4, NumPy 1.26. Runtime models need the models group installed. No provider/network requests are used to train.

```sh
cd backend
export DATA_DIR=/home/ubuntu/hackathon/data
uv sync --group models
uv run --group models python -m matchpulse.models.spadl
uv run --group models python -m matchpulse.models.xg
uv run --group models python -m matchpulse.models.vaep
uv run --group models python -m matchpulse.models.xt
uv run --group models python -m matchpulse.models.sanity
uv run --group models python -m matchpulse.models.backfill
uv run --group models python -m matchpulse.models.backfill --match-id sb:3869685
uv run --group models python -m matchpulse.db.load refresh
uv run --group models python -m matchpulse.models.gamestate_train
uv run --group models python -m matchpulse.models.verify
uv run --group models python -m matchpulse.models.modelcard
```

VAEP uses a disk-backed float32 feature matrix to avoid holding several complete copies in RAM. Game-state caches are fingerprinted against upstream training reports and window/feature definitions and are rebuilt when these change.

## xG

LightGBM binary classifier; 73,598 non-shootout shots across 2,924 matches. Features: distance; visible goal-mouth angle; position; body part; shot type; technique; first-time; pressure; related-pass through ball/cross/cut-back/set piece; freeze-frame availability; opponents inside the triangular shot cone; keeper availability, distance from goal line and perpendicular distance from the shot-to-goal-centre line; pre-shot score difference and minute. Missing keepers remain missing, not zero. Neither shot endpoint/outcome nor StatsBomb xG is a feature.

Uncalibrated held-out probabilities are retained: calibration deciles and total expected goals are already close to observed goals. No calibrator was fitted to evaluation labels. StatsBomb’s benchmark is evaluated on exactly the same shots; its original training overlap is unknown, so this is a reference comparison rather than proof of superiority.

| Held-out metric | MatchPulse | StatsBomb |
| --- | --- | --- |
| log_loss | 0.262877 | 0.262819 |
| brier | 0.075142 | 0.074878 |
| auc | 0.822813 | 0.825041 |
| total_xg | 7992.860490 | 7560.073467 |
| goals | 7996 | 7996 |

Each model’s deciles are sorted by its own prediction (equal-count groups).

| Decile | N | Our mean xG | Our goal rate | SB mean xG | SB goal rate |
| --- | --- | --- | --- | --- | --- |
| 1 | 7360 | 0.011261 | 0.012092 | 0.008757 | 0.019429 |
| 2 | 7360 | 0.019396 | 0.018342 | 0.019352 | 0.018207 |
| 3 | 7360 | 0.026714 | 0.024864 | 0.027327 | 0.021875 |
| 4 | 7359 | 0.035708 | 0.035195 | 0.036199 | 0.030982 |
| 5 | 7360 | 0.046498 | 0.046603 | 0.047027 | 0.039810 |
| 6 | 7360 | 0.060378 | 0.064402 | 0.060411 | 0.062364 |
| 7 | 7359 | 0.081725 | 0.085609 | 0.078132 | 0.087648 |
| 8 | 7360 | 0.119074 | 0.119158 | 0.107987 | 0.119429 |
| 9 | 7360 | 0.203371 | 0.207473 | 0.177443 | 0.207609 |
| 10 | 7360 | 0.481876 | 0.472690 | 0.464564 | 0.479076 |

## VAEP

Two LightGBM classifiers, socceraction’s standard 568 features from three game states, and scores/concedes labels over ten actions (including the current action). 5,962,491 non-shootout actions. Histories and labels reset between periods. Post-action result is intentionally observed: this values completed actions and is not a pre-shot scoring forecast. Reported AUC partly benefits from recognizing already-scored goals.

| Target | Held-out AUC | Held-out Brier | Base rate |
| --- | --- | --- | --- |
| scores | 0.819528 | 0.009392 | 0.011188 |
| concedes | 0.805927 | 0.002111 | 0.002215 |

Values use socceraction’s offensive/defensive differences, its ten-second phase reset, and its fixed penalty (0.792453) and corner (0.046500) prior constants. These are library conventions, not our xG predictions. `vaep_value = offensive_value + defensive_value`. This is action attribution, not an estimate of a player’s causal contribution.

### Player sanity check

Top 20 VAEP per 90, at least 900 observed minutes. Minutes include stoppage and extra time, reconstructed from starting XIs, substitutions and on-pitch dismissals. This corpus overrepresents Barcelona/Messi and selected teams/seasons; rankings are not a population-wide best-player claim.

| Player | Minutes | Total VAEP | VAEP / 90 |
| --- | --- | --- | --- |
| Lionel Andrés Messi Cuccittini | 51805.075550 | 478.922715 | 0.832024 |
| Johan Cruyff | 903.438283 | 7.228329 | 0.720082 |
| Diego Armando Maradona | 1136.330067 | 8.318420 | 0.658838 |
| Jesé Rodríguez Ruiz | 1109.839033 | 8.066969 | 0.654173 |
| Greg Stewart | 1886.614250 | 13.208375 | 0.630099 |
| Gareth Frank Bale | 3305.047767 | 22.619303 | 0.615948 |
| Bartholomew Owogbalor Ogbeche | 1948.859667 | 12.369545 | 0.571236 |
| Cody Mathès Gakpo | 1066.855917 | 6.585028 | 0.555513 |
| Imanol Agirretxe Arruti | 1388.807400 | 8.224894 | 0.533004 |
| Robert Pirès | 3259.814850 | 18.441162 | 0.509141 |
| Nathan Tella | 922.156200 | 5.145170 | 0.502155 |
| Riyad Mahrez | 3416.232483 | 19.032637 | 0.501411 |
| Ronaldo de Assis Moreira | 5046.005283 | 27.976771 | 0.498991 |
| James David Rodríguez Rubio | 2334.751267 | 12.780809 | 0.492675 |
| Deshorn Brown | 914.662750 | 5.003204 | 0.492300 |
| Sergio Leonel Agüero del Castillo | 3342.682417 | 17.947828 | 0.483236 |
| Dimitri Payet | 2970.597550 | 15.863953 | 0.480629 |
| Florian Wirtz | 2834.356800 | 15.099728 | 0.479465 |
| Zlatan Ibrahimović | 4405.053617 | 23.457034 | 0.479253 |
| Kylian Mbappé Lottin | 7122.655883 | 36.918631 | 0.466494 |

### World Cup 2022 final goals

| Minute | Period | Player | Action | Offensive | Defensive | VAEP |
| --- | --- | --- | --- | --- | --- | --- |
| 22.000000 | 1 | Lionel Andrés Messi Cuccittini | shot_penalty | 0.192008 | -0.001141 | 0.190867 |
| 35.000000 | 1 | Ángel Fabián Di María Hernández | shot | 0.766575 | -0.000207 | 0.766367 |
| 79.000000 | 2 | Kylian Mbappé Lottin | shot_penalty | 0.193719 | -0.001690 | 0.192030 |
| 80.000000 | 2 | Kylian Mbappé Lottin | shot | 0.873298 | -0.000338 | 0.872961 |
| 107.000000 | 4 | Lionel Andrés Messi Cuccittini | shot | 0.867670 | -0.000887 | 0.866783 |
| 117.000000 | 4 | Kylian Mbappé Lottin | shot_penalty | 0.188903 | -0.001085 | 0.187818 |

### World Cup 2022 final top 20 actions

| Minute | Player | Action | Result | VAEP | SPADL action index |
| --- | --- | --- | --- | --- | --- |
| 80.000000 | Kylian Mbappé Lottin | shot | success | 0.872961 | 1772 |
| 107.000000 | Lionel Andrés Messi Cuccittini | shot | success | 0.866783 | 2407 |
| 35.000000 | Ángel Fabián Di María Hernández | shot | success | 0.766367 | 710 |
| 79.000000 | Kylian Mbappé Lottin | shot_penalty | success | 0.192030 | 1739 |
| 22.000000 | Lionel Andrés Messi Cuccittini | shot_penalty | success | 0.190867 | 465 |
| 117.000000 | Kylian Mbappé Lottin | shot_penalty | success | 0.187818 | 2477 |
| 35.000000 | Alexis Mac Allister | pass | success | 0.159206 | 709 |
| 104.000000 | Lionel Andrés Messi Cuccittini | pass | success | 0.142176 | 2321 |
| 93.000000 | Cristian Gabriel Romero | pass | success | 0.141063 | 1942 |
| 59.000000 | Ángel Fabián Di María Hernández | cross | success | 0.120377 | 1323 |
| 80.000000 | Marcus Thuram | pass | success | 0.090169 | 1771 |
| 67.000000 | Antoine Griezmann | corner_crossed | success | 0.075416 | 1492 |
| 122.000000 | Gonzalo Ariel Montiel | cross | success | 0.075217 | 2566 |
| 16.000000 | Rodrigo Javier De Paul | cross | success | 0.074126 | 360 |
| 93.000000 | Eduardo Camavinga | pass | success | 0.071849 | 1939 |
| 122.000000 | Ibrahima Konaté | pass | success | 0.071706 | 2553 |
| 59.000000 | Ángel Fabián Di María Hernández | dribble | success | 0.069706 | 1322 |
| 58.000000 | Julián Álvarez | dribble | success | 0.069466 | 1306 |
| 35.000000 | Julián Álvarez | pass | success | 0.066624 | 708 |
| 16.000000 | Lionel Andrés Messi Cuccittini | pass | success | 0.061620 | 359 |

## xT

socceraction ExpectedThreat, 12×8 cells, fitted on the non-shootout actions (moves plus shots to estimate move/shot choice and scoring probabilities). 4,440,132 successful moves receive held-out destination-minus-origin values. Unsuccessful moves and non-moves remain NULL; negative move values are retained. Five match-held-out grids generate action outputs; the final all-match grid and fold grids are in `data/models/xt.json`. No predictive performance claim is made for this descriptive grid.

## Database backfill

493 demo matches; 970,839 UUID-keyed model rows; missing goal-shot xG: 0. The join is `events.extra->>'id' = original_event_id`, scoped by match. Temporary COPY plus one UPDATE FROM; repeated values are skipped. Raw reloads reset model columns; rerun backfill and refresh. The CLI takes optional `--match-id sb:3869685`.

| Raw type | Raw rows | UUID matches | Match rate | VAEP rows | xG rows | xT rows |
| --- | --- | --- | --- | --- | --- | --- |
| 50/50 | 2549 | 0 | 0.000000 | 0 | 0 | 0 |
| Bad Behaviour | 370 | 0 | 0.000000 | 0 | 0 | 0 |
| Ball Receipt* | 467772 | 0 | 0.000000 | 0 | 0 | 0 |
| Ball Recovery | 48502 | 0 | 0.000000 | 0 | 0 | 0 |
| Block | 19755 | 0 | 0.000000 | 0 | 0 | 0 |
| Carry | 374031 | 374031 | 1.000000 | 374031 | 0 | 374031 |
| Clearance | 21575 | 21575 | 1.000000 | 21575 | 0 | 0 |
| Dispossessed | 11697 | 0 | 0.000000 | 0 | 0 | 0 |
| Dribble | 14189 | 14189 | 1.000000 | 14189 | 0 | 0 |
| Dribbled Past | 8454 | 0 | 0.000000 | 0 | 0 | 0 |
| Duel | 37865 | 17403 | 0.459606 | 17403 | 0 | 0 |
| Error | 226 | 0 | 0.000000 | 0 | 0 | 0 |
| Foul Committed | 14829 | 14829 | 1.000000 | 14829 | 0 | 0 |
| Foul Won | 14230 | 0 | 0.000000 | 0 | 0 | 0 |
| Goal Keeper | 15142 | 5598 | 0.369700 | 5598 | 0 | 0 |
| Half End | 2040 | 0 | 0.000000 | 0 | 0 | 0 |
| Half Start | 2040 | 0 | 0.000000 | 0 | 0 | 0 |
| Injury Stoppage | 2159 | 0 | 0.000000 | 0 | 0 | 0 |
| Interception | 9591 | 9591 | 1.000000 | 9591 | 0 | 0 |
| Miscontrol | 13891 | 13891 | 1.000000 | 13891 | 0 | 0 |
| Offside | 197 | 0 | 0.000000 | 0 | 0 | 0 |
| Own Goal Against | 46 | 46 | 1.000000 | 46 | 0 | 0 |
| Own Goal For | 46 | 0 | 0.000000 | 0 | 0 | 0 |
| Pass | 491212 | 487169 | 0.991769 | 487169 | 0 | 351936 |
| Player Off | 534 | 0 | 0.000000 | 0 | 0 | 0 |
| Player On | 534 | 0 | 0.000000 | 0 | 0 | 0 |
| Pressure | 158667 | 0 | 0.000000 | 0 | 0 | 0 |
| Referee Ball-Drop | 794 | 0 | 0.000000 | 0 | 0 | 0 |
| Shield | 736 | 0 | 0.000000 | 0 | 0 | 0 |
| Shot | 12517 | 12517 | 1.000000 | 12517 | 12517 | 0 |
| Starting XI | 986 | 0 | 0.000000 | 0 | 0 | 0 |
| Substitution | 3466 | 0 | 0.000000 | 0 | 0 | 0 |
| Tactical Shift | 1660 | 0 | 0.000000 | 0 | 0 | 0 |

SPADL deliberately excludes raw non-actions such as pressure, ball receipt, lineup and substitutions. Their missing VAEP is intentional, not zero-valued model output. Omitted passes are source-labelled Unknown or Injury Clearance, which socceraction treats as outside play.

## Game-state model: modelled, not causal

Nine LightGBM quantile regressors: p10/p50/p90 for next-15-minute xG for, xG against and possession share. 106,994 five-minute team-perspective windows; 89,450 complete-horizon training/evaluation rows across 2,924 matches. 17,544 late/censored or no-pass future rows remain in the window artifact but are not fitted or scored. Trained 2026-10-04T15:06:51.613373+00:00.

The complete stack is held out: for each outer match fold, xG/VAEP predictors exclude that fold and regenerate both training and test windows, and player ratings exclude the held-out fold plus each row's own match. Final models fit all-match OOF windows. Overlapping windows and paired team perspectives never cross match folds. This is retrospective random-match evaluation, not a forward-season generalization test.

Histories are five minutes within a period. Period timestamps concatenate actual playing-clock durations, including stoppage but excluding interval breaks and shootouts. Future horizons can cross half-time. Possession is a **pass-count share proxy**, not tracked possession time. Field tilt is share of actions beginning beyond 70 metres. Targets are model xG sums, not actual future goals.

**Who is on the pitch.** `lineup_vaep_for/against` sum the on-pitch players' ratings: shrunk VAEP per 90 (900 corpus-average minutes of prior) from every *other* match (`player_ratings.py`). Substitutions and dismissals update the set. This gives `no_sub` and `remove_red_card` a player-specific mechanism: the intervention swaps the incoming player's rating back to the outgoing player's (or restores the dismissed player's). Ratings are career-wide, not strictly prior-in-time: fine for retrospective analysis, not a forecast.

Inference contract: `featurize(window_rows)` selects the ordered feature list below and rejects missing/nonfinite inputs. `predict(features)` returns `{target: {p10: [...], p50: [...], p90: [...]}}`, one aligned value per row, after rearranging crossings, clipping to physical support and applying the outer-quantile calibration factors. Features:

`minute, period, score_diff, possession_share, field_tilt, xg_for, xg_against, vaep_for, vaep_against, xt_for_rate, xt_against_rate, shots_for, shots_against, minutes_since_sub, minutes_since_opponent_sub, players_for, players_against, is_home, international_tournament, lineup_vaep_for, lineup_vaep_against`

| Target | p10 loss | p50 loss | p90 loss | p10–p90 coverage | Mean width | Zero outcomes |
| --- | --- | --- | --- | --- | --- | --- |
| xg_for | 0.0216 | 0.0870 | 0.0639 | 0.879 | 0.564 | 0.176 |
| xg_against | 0.0216 | 0.0870 | 0.0639 | 0.879 | 0.566 | 0.176 |
| possession_share | 0.0192 | 0.0443 | 0.0192 | 0.798 | 0.286 | 0.000 |

**Baselines (held-out median pinball loss, lower is better).** "One fixed range" predicts the same training quantiles for every situation; "in-match only" is the previous 19-feature model without lineup ratings.

| Target | Model | p50 loss | p10–p90 coverage |
| --- | --- | --- | --- |
| xg_for | One fixed range | 0.0912 | 0.900 |
| xg_for | In-match only (old) | 0.0883 | 0.884 |
| xg_for | **This model** | **0.0870** | 0.879 |
| xg_against | One fixed range | 0.0912 | 0.900 |
| xg_against | In-match only (old) | 0.0883 | 0.882 |
| xg_against | **This model** | **0.0870** | 0.879 |
| possession_share | One fixed range | 0.0621 | 0.801 |
| possession_share | In-match only (old) | 0.0496 | 0.794 |
| possession_share | **This model** | **0.0443** | 0.798 |

Skill vs one fixed range: **4.6%** for xG, **28.7%** for possession. Fifteen minutes of xG is dominated by whether a single big chance happens, so the xG band stays wide and only modestly sharper than a constant; possession is far more predictable from team style and quality.

**Calibration.** p10/p90 distance from p50 scaled to minimise out-of-fold pinball loss; reported metrics are cross-fitted (factors fitted on the other four folds) and production uses factors fitted on all out-of-fold forecasts. Factors: {"xg_for": [1.0, 1.02], "xg_against": [1.0, 1.02], "possession_share": [1.02, 1.02]} (1.0 = unchanged; the raw quantiles were already close). Per-quantile checks on held-out rows are the right test here: 15-minute xG is exactly zero in about 18% of windows, so a p10 of 0 makes nominal p10–p90 coverage about 90%, not 80%.

| Target | State | N | Coverage | Mean band width |
| --- | --- | --- | --- | --- |
| xg_for | leading | 22462 | 0.862 | 0.692 |
| xg_for | drawing | 44526 | 0.884 | 0.528 |
| xg_for | trailing | 22462 | 0.886 | 0.507 |
| xg_for | red_card | 4068 | 0.881 | 0.576 |
| xg_for | early | 29240 | 0.877 | 0.528 |
| xg_for | late | 25070 | 0.881 | 0.592 |
| xg_against | leading | 22462 | 0.886 | 0.508 |
| xg_against | drawing | 44526 | 0.884 | 0.530 |
| xg_against | trailing | 22462 | 0.863 | 0.694 |
| xg_against | red_card | 4068 | 0.881 | 0.576 |
| xg_against | early | 29240 | 0.878 | 0.530 |
| xg_against | late | 25070 | 0.881 | 0.593 |
| possession_share | leading | 22462 | 0.795 | 0.284 |
| possession_share | drawing | 44526 | 0.800 | 0.288 |
| possession_share | trailing | 22462 | 0.795 | 0.284 |
| possession_share | red_card | 4068 | 0.790 | 0.277 |
| possession_share | early | 29240 | 0.801 | 0.282 |
| possession_share | late | 25070 | 0.792 | 0.297 |

### Confounding diagnostic

Only score_diff changed from -1 to +1, holding all other held-out features fixed; compare median prediction sensitivity with raw mean outcome association (different estimands, neither causal).

| Diagnostic | xG |
| --- | --- |
| mean_modelled_median_xg_shift | 0.001252 |
| raw_mean_xg_leading | 0.272883 |
| raw_mean_xg_trailing | 0.196543 |
| raw_mean_xg_difference | 0.076341 |

**Goals, substitutions and dismissals are not random.** Strong teams lead more, chasing teams attack differently, and coaches substitute because of fatigue, injury and tactical problems that are only partly observed. These are modelled sensitivities. The API therefore returns the same model's forecast for the real state (`factual`) next to the changed one (`modelled`), their median difference (`effect`) and a `negligible` flag; the UI and the analyst compare those two, never a modelled number with what actually happened. Display analogs and the caveat prominently; never claim what would have happened.

## Pass options: "what if he passed instead of shooting?"

`pass_options.py`. A LightGBM pass-completion model trained on 260,025 open-play passes from the 293 matches with StatsBomb 360 freeze frames. Features: pass geometry plus defenders within 1.5 m and 3 m of the lane, nearest defender to the target and to the passer, defenders within 5 m of the target, distance beyond the offside line (second-last visible defender), passer under pressure, and visible defenders. Pass height, type and body part are excluded because a hypothetical pass has none. Completion rate 85.5%.

| Held-out (5 match folds) | AUC | Brier | Log loss |
| --- | --- | --- | --- |
| With defender positions | 0.9363 | 0.0649 | 0.2118 |
| Geometry only (baseline) | 0.9012 | 0.0736 | 0.2486 |

Calibration deciles (predicted → observed): 0.24→0.24, 0.61→0.61, 0.84→0.83, 0.93→0.93, 0.97→0.97, 0.99→0.99, 0.99→0.99, 1.00→1.00, 1.00→1.00, 1.00→1.00.

At a shot, every teammate in the shot's freeze frame is a pass target: value = P(complete) × max(xG if the receiver shot from there, xT of the receiver's zone). The receiver's xG uses the held-out xG fold model with the same defenders and keeper and assumes a clean first-time strike; the actual shot is scored by the same model, so it matches the app's xG. Both sides are probabilities that the possession ends in a goal. Optimistic by construction (defenders would react, receptions can fail) and always labelled a modelled hypothetical. Example: Kolo Muani's 120+3' chance in the 2022 final, where squaring to Mbappé models above the shot.

## Artifacts and integration

- `processed/spadl/{native_id}.parquet`, `_index.parquet`: all actions, catalogue home team, original UUIDs.
- `processed/xg/shots.parquet`: features, labels, StatsBomb benchmark, fold and held-out xG, including separately identified shootouts.
- `processed/vaep/{native_id}.parquet`: actions, fold, held-out probabilities and three action values.
- `processed/xt/{native_id}.parquet`: action/UUID keys and held-out xT.
- `processed/gamestate_windows.parquet`: all-match OOF features/outcomes and match metadata. Use only complete horizons when displaying 15-minute analog outcomes.
- `processed/gamestate_oof.parquet`: honest outer-fold evaluation predictions/outcomes.
- `models/{xg,vaep,xt,gamestate}.json`: machine-readable metrics, sizes, features and provenance; LightGBM text models alongside.

API workstream: import `gamestate_model.featurize/predict`, select the team perspective and apply the documented feature edit. Load the 2,924-match window artifact for analogs; do not imply those non-demo matches have DB event replay. Refresh/recompute downstream sequence danger and rankings after backfill as appropriate. No schema or fixture shapes were changed.

## Verification

`uv run --group models ruff check .`, `ruff format --check .`, and the 11 tests in `tests/test_models*.py` pass. Checks cover freeze-frame geometry, match folds, cross-half score context, UUID aggregation, synthetic-action exclusion, the final's goal shots, all SPADL action types, window boundaries, goal-kick possession and forecast input contracts.

Read-only acceptance (`python -m matchpulse.models.verify`): 493 DB matches, 12,517 persisted shot xG values, 970,839 VAEP rows, 725,967 xT rows. Final goal xG matches held-out artifacts, and refreshed final timeline xG/VAEP sums match raw event sums. The repeated final-match backfill changed 0 rows. Factual and modified-score predictions run through the saved-model inference API with finite ordered bands. Evidence: `data/models/verification.json`.

## Remaining limits

- StatsBomb open data is selected and historically uneven. Missing freeze frames and reconstructed metadata vary by era; random match folds do not establish unseen-team or future-season performance.
- No tracking data, off-ball movement valuation, fatigue/injury measurements or causal identification. SPADL conventions and proxy possession limit interpretation. Own-goal labels follow socceraction and can omit non-shot own goals. Counterfactuals preserve the observed horizon; they do not resimulate whether extra time occurs.
- Known-corpus xG/VAEP/xT comes from OOF artifacts. Forecast validation is outer-held-out; final game-state inference on known historical windows is in-sample modelled sensitivity. Do not substitute final-model predictions into validation or claim out-of-sample deployment evidence.
- Quantile coverage is empirical for this corpus and the documented window clock/proxies. All final-model future performance remains unverified.

## W12 player-informed models


Generated from artifacts: `2026-10-04T01:59:05.842550+00:00`. W12 explicitly adds a player-model workstream to the older PLAN ownership table. W11 supplies identities; W12 never changes its files.

### Features and leakage boundaries

CC0 Transfermarkt players, player_valuations, games, game_lineups, appearances and clubs are cached under `data/raw/players/transfermarkt/`. Club joins use date, both clubs and explicit name aliases, never scores. Reconstructed Bundesliga dates come from the already-validated bookmaker join. International XIs come from StatsBomb and W11 identities with confidence ≥0.8; unmatched players stay missing.

Pre-match features are home-minus-away differences and mean levels of log(1 + total XI euros), mean log(1 + player euros), log bench value, age at match date, observed earlier international appearances, value of missing usual starters, inferred new-signing share and valuation coverage. Every valuation must be dated strictly before the match; same-day values are excluded. No present-day value, caps, current club or contract snapshot enters a model.

Usual starters started at least three of the team’s previous five observed games, all dated before this match. Clubs use TM lineup history; internationals use prior StatsBomb XIs. Observed caps are the larger of prior TM and SB international appearance counts, a conservative lower bound rather than lifetime caps. Signing share is an imperfect proxy: a player’s first earlier observed appearance at this club must be within 180 days, with an earlier different club observed; established players have at least 180 days at this club. Unknowns stay missing. This is unavailable for national-team selection.

The pre-match candidate is a regularized multinomial correction to the existing walk-forward rating logits. Value, value+age and all-feature sets, with L2 penalties 10 or 100, are scored only on weeks 6–17. Each tuning round fits only earlier rounds. The correction freezes after week 17 while the original ratings continue their established previous-round updates. Missing-value medians and scales use fitting rows only. The original threshold grid and tuning-profit rule are unchanged.

The in-play candidate keeps the incumbent LightGBM parameters and adds log on-pitch value difference plus coverage. Player membership changes only after an observed substitution or on-pitch red card; bench dismissals do not remove active players. All values remain frozen at kickoff. A strength difference is missing unless both sides have values for at least 80% of current players. Strict minute boundaries, the three-minute trading lag, chronological training/calibration/validation partitions, and all tournament exclusions are unchanged.

Candidate selection and retention are distinct. Feature/parameter selection uses tuning data only. Per the requested keep-the-better-model rule, replacement requires both held-out log loss and Brier to improve. The pre-match retention gate therefore uses weeks 18–34 once; it is a post-evaluation deployment decision, not an untouched evaluation of a preselected winner. In-play retention uses the existing 2020–2022 validation partition; tournament results never decide retention. No candidates were retuned after their held-out results.

Retained pre-match: **player-informed candidate**. Retained in-play: **original model**.

Selected pre-match feature set: `value`, L2 `100.0`. Candidate threshold `0.0`, original threshold `0.0`. W11 accepted identities: 5241; TM game joins: 2457/2924.

### Held-out probability scores (lower is better)

| Partition | Predictor | Log loss | Brier |
| --- | --- | --- | --- |
| Pinnacle, weeks 18–34 | before | 0.995752 | 0.592742 |
| Pinnacle, weeks 18–34 | candidate | 0.985647 | 0.584927 |
| Pinnacle, weeks 18–34 | retained | 0.985647 | 0.584927 |
| Pinnacle, weeks 18–34 | market | 0.967149 | 0.573955 |
| In-play validation | before | 0.775768 | 0.457439 |
| In-play validation | candidate | 0.866299 | 0.487824 |
| In-play validation | score_only_baseline | 0.772346 | 0.456493 |
| In-play validation | retained | 0.775768 | 0.457439 |
| All excluded tournament minute rows | before | 0.820001 | 0.485925 |
| All excluded tournament minute rows | candidate | 0.913713 | 0.527870 |
| All excluded tournament minute rows | score_only_baseline | 0.821761 | 0.486576 |
| All excluded tournament minute rows | retained | 0.820001 | 0.485925 |

### Polymarket checkpoint scores

Same aligned cohort and three-minute information lag. Market is normalized three-way historical trade prices; executable mid/ask quotes are unavailable.

| Minute | Matches | Predictor | Log loss | Brier |
| --- | --- | --- | --- | --- |
| 15 | 14 | before | 1.035759 | 0.621732 |
| 15 | 14 | candidate | 0.979784 | 0.609267 |
| 15 | 14 | retained | 1.035759 | 0.621732 |
| 15 | 14 | market | 1.016482 | 0.639074 |
| 30 | 14 | before | 0.975960 | 0.577464 |
| 30 | 14 | candidate | 0.912220 | 0.544694 |
| 30 | 14 | retained | 0.975960 | 0.577464 |
| 30 | 14 | market | 1.130360 | 0.700035 |
| 45 | 14 | before | 0.964061 | 0.581174 |
| 45 | 14 | candidate | 0.914988 | 0.549491 |
| 45 | 14 | retained | 0.964061 | 0.581174 |
| 45 | 14 | market | 0.834078 | 0.492893 |
| 60 | 14 | before | 0.975710 | 0.627034 |
| 60 | 14 | candidate | 0.882199 | 0.537691 |
| 60 | 14 | retained | 0.975710 | 0.627034 |
| 60 | 14 | market | 0.766568 | 0.458205 |
| 75 | 14 | before | 0.799035 | 0.524252 |
| 75 | 14 | candidate | 0.758837 | 0.468887 |
| 75 | 14 | retained | 0.799035 | 0.524252 |
| 75 | 14 | market | 0.899100 | 0.569814 |

### Before, candidate and retained backtests

Identical stake rules, threshold-selection partition, slippage scenarios, settlement and 5,000-draw seed-2026 match-cluster bootstrap. Zero-bet evaluation matches stay in the bootstrap. Candidate results remain visible even when the original is retained. Opening odds remain payout sensitivities, not executable strategies. Pinnacle units and Polymarket dollars are separate.

| Strategy | Version | Bets | P&L | ROI | ROI 95% CI | Brier |
| --- | --- | --- | --- | --- | --- | --- |
| pinnacle-closing-flat | before | 203 | -8.60 | -4.24% | [-31.88%, 29.28%] | 0.592742 |
| pinnacle-closing-flat | candidate | 187 | -10.29 | -5.50% | [-25.31%, 15.76%] | 0.584927 |
| pinnacle-closing-flat | retained | 187 | -10.29 | -5.50% | [-25.31%, 15.76%] | 0.584927 |
| pinnacle-closing-kelly | before | 203 | -401.03 | -13.55% | [-38.98%, 17.21%] | 0.592742 |
| pinnacle-closing-kelly | candidate | 187 | -280.98 | -8.88% | [-30.76%, 14.85%] | 0.584927 |
| pinnacle-closing-kelly | retained | 187 | -280.98 | -8.88% | [-30.76%, 14.85%] | 0.584927 |
| pinnacle-opening-flat | before | 203 | -10.77 | -5.31% | [-31.66%, 25.89%] | 0.592742 |
| pinnacle-opening-flat | candidate | 187 | -12.63 | -6.75% | [-25.91%, 14.23%] | 0.584927 |
| pinnacle-opening-flat | retained | 187 | -12.63 | -6.75% | [-25.91%, 14.23%] | 0.584927 |
| pinnacle-opening-kelly | before | 179 | -271.61 | -8.27% | [-35.04%, 22.74%] | 0.592742 |
| pinnacle-opening-kelly | candidate | 153 | -270.93 | -9.21% | [-35.68%, 19.32%] | 0.584927 |
| pinnacle-opening-kelly | retained | 153 | -270.93 | -9.21% | [-35.68%, 19.32%] | 0.584927 |
| polymarket-0c | before | 42 | +2552.65 | 60.78% | [-1.98%, 122.99%] | 0.586331 |
| polymarket-0c | candidate | 42 | +3189.64 | 75.94% | [14.35%, 138.56%] | 0.542006 |
| polymarket-0c | retained | 42 | +2552.65 | 60.78% | [-1.98%, 122.99%] | 0.586331 |
| polymarket-1c | before | 42 | +2305.58 | 54.89% | [-4.89%, 113.58%] | 0.586331 |
| polymarket-1c | candidate | 42 | +2913.19 | 69.36% | [11.02%, 128.09%] | 0.542006 |
| polymarket-1c | retained | 42 | +2305.58 | 54.89% | [-4.89%, 113.58%] | 0.586331 |
| polymarket-2c | before | 42 | +2080.04 | 49.52% | [-8.01%, 105.64%] | 0.586331 |
| polymarket-2c | candidate | 42 | +2660.70 | 63.35% | [7.96%, 118.92%] | 0.542006 |
| polymarket-2c | retained | 42 | +2080.04 | 49.52% | [-8.01%, 105.64%] | 0.586331 |

### Feature coverage

XI percentages use all 22 starting slots per match as denominator, including unmapped players. Live percentages additionally require a StatsBomb-to-TM identity for the starter. Entire historical competitions are shown so absent source eras cannot disappear from the denominator.

| Competition | Season | Matches | TM games | XI identities | Valued XI | Live valued XI |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Bundesliga | 2015/2016 | 306 | 306 | 100.0% | 100.0% | 99.6% |
| 1. Bundesliga | 2023/2024 | 34 | 34 | 100.0% | 100.0% | 100.0% |
| African Cup of Nations | 2023 | 52 | 0 | 70.8% | 68.0% | 68.0% |
| Champions League | 1970/1971 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Champions League | 1971/1972 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Champions League | 1972/1973 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Champions League | 1999/2000 | 1 | 0 | 13.6% | 0.0% | 0.0% |
| Champions League | 2003/2004 | 1 | 0 | 45.5% | 0.0% | 0.0% |
| Champions League | 2004/2005 | 1 | 0 | 31.8% | 31.8% | 31.8% |
| Champions League | 2006/2007 | 1 | 0 | 54.5% | 54.5% | 54.5% |
| Champions League | 2008/2009 | 1 | 0 | 77.3% | 77.3% | 77.3% |
| Champions League | 2009/2010 | 1 | 0 | 72.7% | 72.7% | 72.7% |
| Champions League | 2010/2011 | 1 | 0 | 86.4% | 86.4% | 86.4% |
| Champions League | 2011/2012 | 1 | 0 | 95.5% | 95.5% | 95.5% |
| Champions League | 2012/2013 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2013/2014 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2014/2015 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2015/2016 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2016/2017 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2017/2018 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2018/2019 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Copa America | 2024 | 32 | 32 | 95.3% | 94.3% | 94.3% |
| Copa del Rey | 1977/1978 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Copa del Rey | 1982/1983 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Copa del Rey | 1983/1984 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA U20 World Cup | 1979 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1958 | 2 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1962 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1970 | 6 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1974 | 6 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1986 | 3 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1990 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 2018 | 64 | 64 | 87.1% | 86.6% | 86.6% |
| FIFA World Cup | 2022 | 64 | 64 | 89.6% | 89.1% | 89.1% |
| Indian Super league | 2021/2022 | 115 | 0 | 29.0% | 19.9% | 19.9% |
| La Liga | 1973/1974 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| La Liga | 2004/2005 | 7 | 0 | 35.7% | 29.9% | 29.9% |
| La Liga | 2005/2006 | 17 | 0 | 40.1% | 36.9% | 36.9% |
| La Liga | 2006/2007 | 26 | 0 | 47.0% | 46.2% | 46.2% |
| La Liga | 2007/2008 | 28 | 0 | 56.3% | 53.7% | 53.7% |
| La Liga | 2008/2009 | 31 | 0 | 68.9% | 68.8% | 68.8% |
| La Liga | 2009/2010 | 35 | 0 | 78.2% | 77.5% | 77.5% |
| La Liga | 2010/2011 | 33 | 0 | 88.0% | 87.6% | 87.6% |
| La Liga | 2011/2012 | 37 | 0 | 92.4% | 91.6% | 91.6% |
| La Liga | 2012/2013 | 32 | 32 | 93.5% | 93.5% | 93.5% |
| La Liga | 2013/2014 | 31 | 31 | 100.0% | 99.7% | 99.7% |
| La Liga | 2014/2015 | 38 | 38 | 100.0% | 99.6% | 99.6% |
| La Liga | 2015/2016 | 380 | 380 | 100.0% | 99.5% | 99.5% |
| La Liga | 2016/2017 | 34 | 34 | 100.0% | 99.9% | 99.9% |
| La Liga | 2017/2018 | 36 | 36 | 100.0% | 100.0% | 100.0% |
| La Liga | 2018/2019 | 34 | 34 | 99.5% | 99.5% | 99.5% |
| La Liga | 2019/2020 | 33 | 33 | 100.0% | 100.0% | 99.9% |
| La Liga | 2020/2021 | 35 | 35 | 100.0% | 100.0% | 100.0% |
| Liga Profesional | 1981 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Liga Profesional | 1997/1998 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Ligue 1 | 2015/2016 | 377 | 377 | 100.0% | 99.5% | 99.5% |
| Ligue 1 | 2021/2022 | 26 | 26 | 100.0% | 100.0% | 100.0% |
| Ligue 1 | 2022/2023 | 32 | 32 | 100.0% | 99.9% | 99.9% |
| Major League Soccer | 2023 | 6 | 0 | 80.3% | 79.5% | 79.5% |
| North American League | 1977 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Premier League | 2003/2004 | 38 | 0 | 23.1% | 0.0% | 0.0% |
| Premier League | 2015/2016 | 380 | 380 | 100.0% | 99.6% | 99.6% |
| Serie A | 1986/1987 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Serie A | 2015/2016 | 380 | 380 | 100.0% | 100.0% | 99.7% |
| UEFA Euro | 2020 | 51 | 51 | 92.0% | 91.6% | 91.6% |
| UEFA Euro | 2024 | 51 | 51 | 91.7% | 91.2% | 91.2% |
| UEFA Europa League | 1988/1989 | 3 | 0 | 0.0% | 0.0% | 0.0% |

### Limitations and integration

Valuations are noisy estimates, not player ability or transfer prices. Historical rows were downloaded today and may have been retrospectively revised; strict dates do not establish archived publication vintages. W11 matching confidence is a heuristic, not a calibrated probability. Incomplete identities and valuations can bias summed strengths downward. The 80% live coverage guard limits but does not eliminate this. Missing history is not evidence of no international experience or no absences. First observed club appearances are not verified signing dates. Current lifetime caps are deliberately excluded.

The game-state model and its API are unchanged; the optional quantile experiment was not run. No claim of improved pinball loss or coverage is made. The same small selected Polymarket cohort, retrospective goal alignment and unproven fills remain material limitations. No new profitability conclusion can rely on paper P&L alone.

The requested additive `comparison` and `model_versions` fields live in the strict backtest schema. All old fields and market response shapes remain. W12 writes served artifacts under `data/processed/backtest/w12/`; the new route prefers them. This prevents the old shared process from reading a payload its older strict schema rejects. The orchestrator must merge and reload the API to expose W12 on :8000. W12 does not restart it. The two authorized backend golden snapshots are regenerated; fixtures/ remains orchestrator-owned and needs the corresponding additive update.

Reproduce: `DATA_DIR=/home/ubuntu/hackathon/data uv run --group models python -m matchpulse.backtest squads`, then `python -m matchpulse.backtest.squad_report`. The immutable `w12_before/` snapshot preserves original scores, predictions, strategy results and model bundle. Candidate predictions, candidate backtests, complete join/coverage audits and model JSON cards remain beside it. Models and data are gitignored.

Verification is recorded in `data/processed/backtest/w12/verification.json`; run the full suite plus `pytest matchpulse/backtest/test_squads.py`. Use :8050 for acceptance and stop it afterwards.

Executed acceptance: 101 passed, 4 dependency deprecation warnings; owned-file lint/format passed; 80 market responses and 1154 series points verified on :8050. 81 original served artifacts remain byte-identical. Acceptance server stopped; shared :8000 never restarted.

## W14 reproducible candidates (2026-10-05)

Production artifacts above remain unchanged. `models.evaluate` writes only below
`data/models/candidates/`, pins input hashes/splits, and distinguishes historical
card inventory from fresh held-out predictions. Binary Brier is mean squared
error; three-class Brier sums squared class errors. ECE uses ten fixed-width bins
(binary positive class, multiclass mean one-vs-rest). Paired 95% intervals resample
5,000 whole matches with seed 2026, retaining correlated windows. These intervals
condition on the fitted models and do not include model-selection uncertainty.

`inplay-v1`: six frozen regularization/feature recipes, pre-2018 fitting, 2018
selection, 2019 temperature calibration. The selected seven-leaf full-feature
candidate has validation Brier 0.457473 vs incumbent 0.457439; log loss 0.776516 vs
0.775768. Both paired intervals include zero; reject promotion. Score-only baseline
remains 0.456493 / 0.772346. No test outcomes select a recipe or calibration.

`xg-v1`: nested five-match-fold recipe search; for each outer fold, the next fold
selects from six recipes fitted on the other three folds. The selected recipe
refits on the four outer training folds. Fresh incumbent fold predictions use
identical held-out shots. Log-loss change -0.000164881, 95% paired interval
[-0.000411858, 0.000072213]; Brier change -0.000009562, interval
[-0.000084483, 0.000065408]. Small point gains are inconclusive; no promotion yet.
The production recipe is chosen by outer-0 inner selection, never outer results.
All six booster filenames and inference feature order remain compatible.

Full results, negative experiments and remaining work: `docs/models/LOG.md`.
Candidate swap/backfill/dependency instructions: `docs/models/PROMOTION.md`.

The first `goals-v1` and `gamestate-v1` results are **withdrawn**. Dropping outer
matches from global OOF player totals did not exclude those matches from the
upstream VAEP estimators. `outer_player_ratings` now revalues training-only matches
using the held-out fold's VAEP boosters, then aggregates ratings; training rows
also exclude themselves from the shrinkage prior. Production rating construction
is unchanged. `corrected_windows` writes audited candidate-local caches, and
future `windows` builds use the repaired outer path.

`goals-v2` keeps the original predeclared 500-tree/seven-leaf/min-child-500/L2-20
recipe. Both it and the current recipe are refitted on identical repaired folds:
next-15 Poisson deviance 0.701315 → 0.700360 (paired delta CI
[-0.001398762, -0.000499137]); remaining-goals deviance 0.968991 → 0.965367
(CI [-0.004933028, -0.002319564]); block-result Brier 0.406973 → 0.406049
(CI [-0.001382730, -0.000465010]). Recommend orchestrator review of **v2 only**.
The comparison normalizes truncated Poisson mass identically for both models and
records missing mass. API helper, booster feature order and signatures remain
unchanged. All what-if outputs remain modelled, not causal.

`gamestate-v2` refits raw quantiles on repaired folds. Possession p50 pinball
improves 0.0443413 → 0.0442824 (CI [-0.000104324, -0.000012014]); its p10 and p90
also improve. xG-target results are mixed; hold the bundle. Archived calibrated
metrics are explicitly labelled historically invalid, not used as a comparator.
`prematch-v1` worsens Brier 0.584927 → 0.585351, still worse than market 0.573955.
`passes-v1` has inconclusive, opposing Brier/log-loss changes on 293 match folds.
`xt-v1` tests fixed lateral-symmetry pooling, preserving grid format: 99-class
next-action log loss 2.791217 → 2.789602 improves, Brier 0.883531 → 0.883575 worsens.
Both changes have paired intervals excluding zero; hold. Player rank Spearman
0.999923 and 20/20 top-rank overlap are descriptive sanity checks only.
