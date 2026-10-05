# W14 round 2: models for the new data

Great first round: the evaluation harness, the leakage repair and honest negative results are exactly what we want. The takeaway is that on the existing 2,924 StatsBomb matches most models sit near their ceiling (gains in the 4th decimal). The big improvements now come from **new data**, and W13 is bringing in a lot of it:

* **Shots-only ("lite") matches:** 2,002 Understat matches are already staged (`data/sources/`, `matchpulse_staging`), and FotMob top-5 + Champions League matches are coming.
* **Full Opta event streams from WhoScored** (`ws:` IDs), possibly thousands of recent top-5 + Champions League matches, converted to SPADL under `data/sources/whoscored/`. W13 is working on this right now. Watch `~/hackathon-W13-sources/docs/sources/LOG.md`.

Same rules as round 1 (AGENTS.md §3, §5, §11; candidates only; honest grouped held-out validation; nice, 8 threads, under 12 GB).

## Tasks, in order

1. **Shot-only xG for lite matches.** AGENTS.md says xG is always our own model's value, but lite matches have no event context. Build `xg_shot` (candidate name `xg-shot-v1`) using only features that Understat and FotMob both provide (location, body part, situation / set piece / penalty, shot type, assist type, game state if available). Train and validate on StatsBomb shots with those same reduced features. Report its log loss, Brier and calibration against the full xG model on the same held-out shots, so we know how much is lost. Then check it on Understat/FotMob shots against their provider xG as a sanity check (not a target). Give it a pure inference function the W13 loader can call, and document it in `INTEGRATION.md` and PROMOTION.md.
2. **Cross-provider transfer for Opta/WhoScored SPADL.** As soon as W13 has WhoScored SPADL, measure the source effect. Score the current xG / VAEP / xT on WhoScored matches: calibration, plus goals predicted vs actual per competition. Then test training on StatsBomb + WhoScored (with a source indicator or provider-specific calibration where definitions differ), evaluated separately on StatsBomb held-out and WhoScored held-out folds. Recent matches are where the product is going, so a model that's good on Opta-sourced recent matches matters more than a 4th-decimal gain on StatsBomb.
3. **In-play and pre-match with many more matches.** Once there are thousands of recent matches (full or lite, with results), rebuild the in-play and pre-match backtests with rolling time-ordered folds and rerun the comparisons against the naive baseline and the market.
4. **Lite-match outputs for the product:** which model outputs can we honestly produce for a shots-only match (e.g. our xG per shot, chance totals, a simple "who was on top" from shots, goals-model outlook at a minute from score + shot xG so far)? Prototype them as pure functions, validate on StatsBomb matches by degrading them to shots only, and document them for W13/the API.
5. If W13's data isn't ready when you get to tasks 2–3, do 1 and 4 first, then go back to the inconclusive ones (xG, in-play) with the methods from your LOG's "next experiments", but don't burn compute chasing 4th-decimal gains.

Keep `docs/models/LOG.md` and PROMOTION.md current, commit in small steps on `ws/W14-models`, and end with the handoff table as before. Also say clearly which candidates are safe to promote now.
