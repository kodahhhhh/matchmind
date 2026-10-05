# Proposal: source capabilities and full/lite matches

This is an orchestrator handoff, not a fixture/schema migration. No production
API, schema, fixture or frontend file is changed by W13.

## Match identity and discovery

Add `data_tier: "full" | "lite"` to match cards and match detail. Old StatsBomb
matches default to `full`. Include `source` and a capability object. Tier alone
does not imply tracking, freeze frames, calibrated transfer or pass options.

Merge `data/sources/catalogue_<source>.json` into the main catalogue only after
checking source rights and dedupe reports. Read entries independent of `demo`;
derive `has_detail` from the loaded tier/capabilities rather than hardcoding true.
Keep same source-prefixed match IDs: `af:<native>`, `us:<native>`, `fm:<native>`.
Numeric team/player IDs stay within JavaScript's safe integer range. Source IDs
and reviewed StatsBomb bridges are retained in a separate identity map.

## Feature matrix

| Endpoint / feature | Full stream | Lite / shot tier |
|---|---|---|
| Competition list / match cards | Available when loaded | Available; visible “Shots & stats” label |
| Match meta / score / available rosters | Available | Available; unavailable jersey/position/time fields nullable |
| Pitch / `/events` | All supported observed actions | Do not send a shot subset as a full stream; serve `/shots` or a discriminated event collection |
| `/timeline` | Our per-minute possession, field tilt, xG, VAEP momentum | Own cumulative shot xG and goal markers only; provider momentum is a separately labelled optional series |
| Replay | Observed action replay | Shot-by-shot navigation; no passing/carry animation invented |
| Top sequences / sequence danger | Inferred/provider possession runs, with provenance | Unavailable: no possessions or complete action order |
| Player VAEP rankings | Available with real action values | Unavailable; show goals/shots/own xG or clearly labelled provider ratings |
| Turning points | Existing full-action momentum method | Disabled until a separate shot-tier method is implemented and validated |
| What-if / game-state / analogs | Only where identity/context/model requirements are met | Disabled; no missing possession/lineup values supplied as zeros |
| Pass options | Only with usable player freeze frames/tracking | Disabled, even if lineups have average pitch positions |
| Analyst / citations | Existing event/sequence tools | Restrict tool set to available shots, score and actual stats; disable full-window/VAEP/counterfactual tools |
| Commentary / search | Regenerate from accepted full source events | Shot-specific summaries only; no fabricated sequence summaries |

The current API treats `extra` as StatsBomb-shaped raw events, reads only
demo-enabled catalogue entries, and requires rows in `events` for every bundle.
Consequently a staging lite payload is deliberately stored in
`source_lite_matches`, not `events` or `minute_metrics`. Running the current API
with a lite catalogue entry returns 503 for missing events; that is an integration
gap, not a successful lite endpoint. The orchestrator should implement typed
dispatch and capability checks before exposing the entry.

Schema-valid full responses also need semantic availability checks. The current
shared metrics layer defaults absent pressure to `false`, requires integer jersey
numbers, and substitutes a threat proxy when a row lacks VAEP. W13 retains missing
context/model values in source exports and DB rows; shared serialization should
preserve unavailable values and identify any deliberate proxy rather than label
it as our model's result. Passing the legacy schema does not validate these defaults.

## Example lite metadata (proposal)

```json
{
  "match_id": "us:31229",
  "source": "us",
  "data_tier": "lite",
  "competition": "Premier League",
  "season": "2026/2027",
  "match_date": "2026-09-20",
  "teams": {
    "home": {"name": "Fulham"},
    "away": {"name": "Manchester United"}
  },
  "score": {"home": 1, "away": 1},
  "capabilities": {
    "shots": true,
    "lineups": true,
    "team_stats": false,
    "provider_team_stats": true,
    "player_ratings": false,
    "provider_momentum": false,
    "full_events": false,
    "vaep": false,
    "xt": false,
    "game_state": false,
    "pass_options": false
  },
  "clock_precision": "minute",
  "xg_provenance": "MatchPulse current model; cross-source transfer unvalidated"
}
```

The example uses real source identity/date/score, but the final teams object must
also include the existing canonical IDs/short names/colours. Example isn't a new
fixture and doesn't authorize changing existing response shapes.

## Shot and timeline rules

- Every `xg` is an actual result from our current model. Retain Understat/FotMob
  xG as `provider_xg`, with provider name, never copy it into `xg` or `sb_xg`.
- Spatial storage is SPADL metres with bottom-left origin and the acting team
  attacking +x. Rotate away shots at the API boundary for home attacking +x.
- Understat exposes minute only, no half/second. Preserve `period: null`,
  `second: null`, `time_precision: "minute"`; minute 47 could mean either
  first-half stoppage or second half. Don't derive exact elapsed `t` or seconds.
- Timeline records should make unavailable possession/field tilt/VAEP/momentum
  `null` or omit those series under a discriminated lite response. Never emit
  50%/0/empty complete-event statistics just to satisfy the old full schema.
- Provider momentum must have a separate method/provenance and axis; it has a
  different scale and meaning from our VAEP momentum.
- Understat league-history PPDA/deep entries are joined only by exact team/date/
  side. Preserve these as `provider_team_stats`, not our full-event metrics.
- Unknown statistics remain unavailable; a genuine zero shot count is zero only
  when complete provider shot coverage is established.
- Model transfer uncertainty matters even for a full source: Dynasty is youth
  football, some body parts/context are absent, and clocks originate in video
  metadata. Our exported xG/VAEP are experimental transfer predictions.

## Frontend behaviour

Show score, available rosters, shot map and cumulative own xG. A concise “Shots &
stats” badge distinguishes lite entries. Hide sequence/VAEP/what-if/pass-option
tabs when capability flags are false; don't leave empty leaderboards or dead
buttons. Label optional source ratings and momentum by provider. Minute-only
shots support navigation/citations without promising exact replay timing.

## Requests for API/model/frontend workstreams

1. Add tier/capability fixtures and schema variants together, including error
   responses for unavailable capabilities; then implement repository dispatch.
2. Remove the hard demo-only catalogue filter and derive availability from DB
   state. Test full-source and lite-source discovery separately from StatsBomb.
3. Add native period start/duration metadata for youth/video-clock providers;
   current analytics assume second half begins at match minute 45. W13 keeps this
   nominal mapping explicit rather than claiming verified broadcast clock times.
4. W14: validate cross-source/domain transfer, missing-context features and
   current model calibration on held-out source matches before promotion. Adapt
   game-state/window IO away from hardcoded StatsBomb/native-ID file paths and
   require valid cross-source player rating identities. No pass-options support
   is promised without tracking/freeze frames.
5. Resolve provider publication/automation permissions before production
   exposure, especially FotMob and Understat. Champions League remains uncovered
   by the permitted shot-tier acquisition used here.
