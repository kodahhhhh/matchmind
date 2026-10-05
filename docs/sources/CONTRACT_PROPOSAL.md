# Full/lite contract — implemented in W13 round 2

Round 2 grants W13 API and new-fixture ownership. Repository dispatch and optional
schema fields are implemented; existing StatsBomb fixtures remain unchanged. All
20 tests in the unchanged `tests/test_contract.py` pass against staging with an
isolated StatsBomb reference catalogue. New source discovery is tested separately
because its match count intentionally exceeds the test's fixed baseline of 2,924.

## Discovery and identity

Loaded source matches join the catalogue when `DATA_DIR/sources/` exists. DB
metadata supplies source entries; unloaded exports are not advertised. Discovery
refreshes every five minutes. The existing StatsBomb catalogue remains intact.
Exact date, reviewed team aliases and team-keyed scores dedupe loaded matches:
StatsBomb → other full streams → FotMob → Understat. Conflicting scores stay
visible for review. Source-local IDs remain stable; superseded lite IDs aren't
advertised as duplicate cards. `sources/reconciliation_report.json` records aliases.

Per-source catalogue files retain provenance. The orchestrator should merge
`data/sources/catalogue_canonical.json` for new sources, or apply the recorded
alias decisions when merging individual `catalogue_<source>.json` files. Do not
merge both canonical and per-source catalogues as independent match lists.

## Optional metadata

New source match detail includes `data_tier`, `source`, `capabilities`; lite cards
include `data_tier: "lite"` and capabilities. Legacy StatsBomb responses omit the
new fields, preserving existing serialization. Missing jersey numbers are null
for new sources. Capability flags govern features independently of tier: full
Wyscout/WhoScored data still lacks freeze frames and validated game-state identity
coverage, so `pass_options` and `game_state` are false.

| Endpoint or feature | Full stream | Lite tier |
|---|---|---|
| `/competitions`, `/matches` | Loaded sources plus existing catalogue | Loaded score/date/team cards, “Shots & stats” label |
| Match meta | Existing shape; optional source capabilities | Score, available rosters, shot goal markers and separately labelled provider data |
| `/events` | All mapped observed actions; synthetic converter carries explicitly identified in stored provenance | Shots only, in existing event shape; no artificial passes/carries/sequences |
| `/timeline` | Existing possession, field tilt, own xG, VAEP momentum | Observed shot buckets with own xG and cumulative own xG; possession, field tilt, passes, VAEP and momentum **null** |
| Replay | Action replay where the source clock exists | Shot-by-shot navigation, displayed minute; exact `t`, `second`, `duration_t` null |
| `/sequences`, `/players`, `/turning-points` | Existing analytics | Empty collections; hide their full-event analytical panels |
| `/counterfactual`, shot alternatives | Require full stream and declared supporting capability | HTTP 422 before invoking models |
| `/ask` | Existing analyst | HTTP 422 before invoking full-event tools |
| `/commentary` | Existing stored commentary | Empty collection; no invented sequence narratives |

## Shot and timeline semantics

- Every `xg` is our current model prediction. Provider xG remains in raw/exported
  `provider_xg`; it is never copied to `xg` or `sb_xg`.
- Lite spatial storage uses attacking-relative 105×68 metres, bottom-left y.
  Rotate away shots once at the API boundary, so home attacks +x in both halves.
- Understat has no shot period or second. Preserve `period: null`, `second: null`,
  `t: null`, `time_precision: "minute"`. FotMob has a period but no second, so
  `t` remains null. Do not derive exact elapsed time from minute-only evidence.
- `sequence_id` and `under_pressure` are null on lite shots. No sequence or
  pressure observation is implied by a shot map. Shot endpoint coordinates are
  null unless supported; raw blocked/goal-crossing provider fields remain raw.
- `/events?from=...&to=...` uses elapsed seconds for full matches. Lite requests
  with an elapsed filter return 422 because that precise clock is unavailable.
- `duration_t` is null and `periods` is empty for lite matches. The timeline
  contains **observed shot buckets**, not a fabricated complete minute grid.
- Own goals can appear as shot-map markers, but get no shot xG and do not inflate
  the shot-model timeline. Their benefiting team is used in goal markers.
- A side's observed bucket has zero shots/xG when only the other side shot there.
  An unscored observed shot makes that bucket/cumulative model value null; this
  never silently becomes provider xG or a falsely complete total.
- Provider momentum, team stats and player ratings are separate optional meta
  fields. They are not our VAEP momentum or player impact ratings. Understat
  PPDA/deep enrichments and FotMob aggregates remain separate provider objects.

## Frontend integration request

W15 already reads tier/full-event/VAEP flags and null timeline series. It must
also accept nullable `t`, `second`, unknown `period`, `duration_t`, jersey and
sequence IDs. Shot navigation should use list order and displayed minute; avoid
continuous time animation and elapsed-range filtering on lite matches. Hide
unsupported analytics, rather than showing empty rankings or disabled controls.
Use provider names on provider ratings/momentum/stat panels. `fixtures/matches/
fm_5795459/` contains a real cached lite response example.

## Remaining model requests

W14 should validate transfer/calibration on the exported source SPADL and
missing-context features. Existing game-state/what-if paths still assume
StatsBomb file paths and player-rating identities. New source game-state and
pass-option capabilities remain false until those requirements are met. Inferred
socceraction carries and inferred control-run sequences are not provider
possession annotations. Model transfer is explicitly unvalidated.
