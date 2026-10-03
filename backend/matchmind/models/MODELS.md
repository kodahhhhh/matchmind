# MatchMind custom models

Measured training run: 2026-10-03T22:52:31.690662+00:00. CPU only. StatsBomb open-data source commit `4b73468`; catalogue, not the incomplete source match index, selects the corpus.

## Data, reproducibility and validation

2,924 men’s matches; 5,962,767 SPADL actions; 0 conversion failures. The 493 demo matches are a subset of training, but every displayed xG, VAEP and xT is held out by match. Synthetic SPADL dribbles have no raw UUID and are excluded from the DB join. Split interception/pass actions are summed back to one raw UUID. Stored SPADL has home attacking +x; spatial training rotates each acting team to +x. DB raw coordinates are unchanged.

Five deterministic shuffled match folds (seed 2026) are shared across models. No action-level random split. Shootouts receive held-out xG/VAEP predictions for event completeness, but are excluded from training, evaluation, rankings, windows and timeline sums. Finals below exclude shootouts. All artifacts remain gitignored. Final models fit all eligible training matches; match artifacts use held-out models.

The `models` dependency group pins socceraction 1.5.3 and multimethod <2 for its pandera compatibility. Python 3.12, pandas 2, LightGBM 4, NumPy 1.26. Runtime models need the models group installed. No provider/network requests are used to train.

```sh
cd backend
export DATA_DIR=/home/ubuntu/hackathon/data
uv sync --group models
uv run --group models python -m matchmind.models.spadl
uv run --group models python -m matchmind.models.xg
uv run --group models python -m matchmind.models.vaep
uv run --group models python -m matchmind.models.xt
uv run --group models python -m matchmind.models.sanity
uv run --group models python -m matchmind.models.backfill
uv run --group models python -m matchmind.db.load refresh
uv run --group models python -m matchmind.models.gamestate_train
uv run --group models python -m matchmind.models.modelcard
```

VAEP uses a disk-backed float32 feature matrix to avoid holding several complete copies in RAM. Game-state caches are fingerprinted against upstream training reports and window/feature definitions and are rebuilt when these change.

## xG

LightGBM binary classifier; 73,598 non-shootout shots across 2,924 matches. Features: distance; visible goal-mouth angle; position; body part; shot type; technique; first-time; pressure; related-pass through ball/cross/cut-back/set piece; freeze-frame availability; opponents inside the triangular shot cone; keeper availability, distance from goal line and perpendicular distance from the shot-to-goal-centre line; pre-shot score difference and minute. Missing keepers remain missing, not zero. Neither shot endpoint/outcome nor StatsBomb xG is a feature.

Uncalibrated held-out probabilities are retained: calibration deciles and total expected goals are already close to observed goals. No calibrator was fitted to evaluation labels. StatsBomb’s benchmark is evaluated on exactly the same shots; its original training overlap is unknown, so this is a reference comparison rather than proof of superiority.

| Held-out metric | MatchMind | StatsBomb |
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

Nine LightGBM quantile regressors: p10/p50/p90 for next-15-minute xG for, xG against and possession share. 106,994 five-minute team-perspective windows; 89,450 complete-horizon training/evaluation rows across 2,924 matches. 17,544 late/censored or no-pass future rows remain in the window artifact but are not fitted or scored.

The complete stack is held out: for each outer match fold, xG/VAEP predictors exclude that fold and regenerate both training and test windows. Final models fit all-match OOF windows. Overlapping windows and paired team perspectives never cross match folds. This is retrospective random-match evaluation, not a forward-season generalization test.

Histories are five minutes within a period. Period timestamps concatenate actual playing-clock durations, including stoppage but excluding interval breaks and shootouts. Future horizons can cross half-time. Possession is a **pass-count share proxy**, matching the raw DB convention, not tracked possession time. Field tilt is share of actions beginning beyond 70 metres; an empty denominator yields 0.5 and is not evidence of equal control. Targets are model xG sums, not actual future goals.

Inference contract: `featurize(window_rows)` selects the ordered feature list below and rejects missing/nonfinite inputs. `predict(features)` returns `{target: {p10: [values], p50: [values], p90: [values]}}`, with one aligned value per row. Quantiles are rearranged to remove crossings and clipped to physical support. The API must use the same five-minute feature definitions. Features:

`minute, period, score_diff, possession_share, field_tilt, xg_for, xg_against, vaep_for, vaep_against, xt_for_rate, xt_against_rate, shots_for, shots_against, minutes_since_sub, minutes_since_opponent_sub, players_for, players_against, is_home, international_tournament`

| Target | p10 loss | p50 loss | p90 loss | p10–p90 coverage | Mean width | Zero outcomes |
| --- | --- | --- | --- | --- | --- | --- |
| xg_for | 0.021630 | 0.088345 | 0.065384 | 0.883522 | 0.565522 | 0.176467 |
| xg_against | 0.021627 | 0.088349 | 0.065417 | 0.881733 | 0.565357 | 0.176467 |
| possession_share | 0.021365 | 0.049616 | 0.021368 | 0.794298 | 0.318316 | 0.000000 |

Coverage is inclusive, evaluated against held-out outcomes; zero-inflated xG targets need not achieve exactly 80% with deterministic quantiles. Bands describe outcome spread, not confidence intervals on a causal effect.

| Target | State | N | Coverage | Mean band width |
| --- | --- | --- | --- | --- |
| xg_for | leading | 22462 | 0.874588 | 0.695604 |
| xg_for | drawing | 44526 | 0.885977 | 0.521886 |
| xg_for | trailing | 22462 | 0.887588 | 0.521940 |
| xg_for | red_card | 4068 | 0.882989 | 0.585067 |
| xg_for | early | 29240 | 0.883618 | 0.528643 |
| xg_for | late | 25070 | 0.885441 | 0.592613 |
| xg_against | leading | 22462 | 0.886608 | 0.521484 |
| xg_against | drawing | 44526 | 0.884652 | 0.522234 |
| xg_against | trailing | 22462 | 0.871071 | 0.694712 |
| xg_against | red_card | 4068 | 0.879056 | 0.584878 |
| xg_against | early | 29240 | 0.881361 | 0.528865 |
| xg_against | late | 25070 | 0.883566 | 0.591520 |
| possession_share | leading | 22462 | 0.794898 | 0.319590 |
| possession_share | drawing | 44526 | 0.794210 | 0.317209 |
| possession_share | trailing | 22462 | 0.793874 | 0.319237 |
| possession_share | red_card | 4068 | 0.789577 | 0.304536 |
| possession_share | early | 29240 | 0.797640 | 0.315055 |
| possession_share | late | 25070 | 0.788991 | 0.326131 |

### Confounding diagnostic

Only score_diff changed from -1 to +1, holding all other held-out features fixed; compare median prediction sensitivity with raw mean outcome association (different estimands, neither causal).

| Diagnostic | xG |
| --- | --- |
| mean_modelled_median_xg_shift | 0.023925 |
| raw_mean_xg_leading | 0.272883 |
| raw_mean_xg_trailing | 0.196543 |
| raw_mean_xg_difference | 0.076341 |

**Goals, substitutions and dismissals are not random.** Strong teams lead more, chasing teams attack differently, and coaches substitute because of fatigue, injury and tactical problems that are only partly observed. Changing score difference while holding recent xG/VAEP fixed creates an artificial state; it does not remove the goal’s downstream consequences. `no_sub` must restore the prior substitution age (or elapsed minutes if none), and `remove_red_card` restores only the affected player count. These are modelled sensitivities. Display analogs and the caveat prominently; never claim what would have happened.

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

Read-only acceptance (`python -m matchmind.models.verify`): 493 DB matches, 12,517 persisted shot xG values, 970,839 VAEP rows, 725,967 xT rows. Final goal xG matches held-out artifacts, and refreshed final timeline xG/VAEP sums match raw event sums. The repeated final-match backfill changed 0 rows. Factual and modified-score predictions run through the saved-model inference API with finite ordered bands. Evidence: `data/models/verification.json`.

## Remaining limits

- StatsBomb open data is selected and historically uneven. Missing freeze frames and reconstructed metadata vary by era; random match folds do not establish unseen-team or future-season performance.
- No tracking data, off-ball movement valuation, fatigue/injury measurements or causal identification. SPADL conventions and proxy possession limit interpretation. Own-goal labels follow socceraction and can omit non-shot own goals. Counterfactuals preserve the observed horizon; they do not resimulate whether extra time occurs.
- Known-corpus xG/VAEP/xT comes from OOF artifacts. Forecast validation is outer-held-out; final game-state inference on known historical windows is in-sample modelled sensitivity. Do not substitute final-model predictions into validation or claim out-of-sample deployment evidence.
- Quantile coverage is empirical for this corpus and the documented window clock/proxies. All final-model future performance remains unverified.
