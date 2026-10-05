# Sources — EC2 evidence, 2026-10-05, round 2

The owner now accepts responsibility for source terms and licences. Those remain
recorded below, but missing licences or restrictive terms do not exclude sources.
Round 1's exclusions are superseded. HTTP acquisition identifies as MatchPulse,
is sequential and at least 1.1 seconds apart per host. Genuine headed Chromium
uses its ordinary browser identity; page loads are at least 3.1 seconds apart.
Complete raw responses are immutable under `data/raw/<source>/`. Remaining
refusals stop the source: no CAPTCHA service, proxy network or overload.

| Source | EC2/browser evidence | Full on-ball events x/y | Shots / xG | Other available fields | Coverage / recency | Licence / terms | Decision |
|---|---|---|---|---|---|---|---|
| WhoScored | Competition, fixtures and match-centre each **403**, title “Attention Required! \| Cloudflare”; unchanged after 30 seconds in genuine headed Chromium. No embedded event data reached. | Opta event stream documented in `matchCentreData`; not acquired here | Full stream includes shots; our models required | Qualifiers, teams, players, clock, lineups when captured | Discovery targets top five + Champions League, 2023/24 through current, newest first | Proprietary site/provider data; owner responsibility | Home-connection uv/Playwright/rsync fetcher and offline Opta→SPADL importer built. Live usable-connection discovery remains unverified. See WHOSCORED_LOCAL.md |
| Wyscout / Figshare | API 403 in round 1; article **202** remained blank after 30 seconds. Genuine Chromium public download host **successfully delivered all five dataset files** | Yes, full historical streams | Shots; no provider xG needed | Real teams/players/rosters, outcomes/tags, clocks; no shirt-number coverage | 1,941 source matches: big five 2017/18, Euro 2016, World Cup 2018 | [Collection](https://figshare.com/collections/Soccer_match_event_dataset/4415000), **CC BY 4.0**, Pappalardo et al. 2019 | Bulk offline SPADL/model inference/staging import, dedupe StatsBomb; W14 parquet exports. No manual owner download needed |
| FotMob public JSON | `/api/data/leagues` and `/api/data/matchDetails` **200**; legacy `/api/leagues` 404 cached | **No**, inspected detail has shot maps and match-fact markers, no every-action stream | x/y in 105×68 metre pitch, provider xG kept separate; own xG scored | Starting/bench lineups, ratings, stats, proprietary momentum; some physical summaries | Top five + Champions League, 2025/26 and 2026/27 bootstrap; actual latest date in LOG | [Terms](https://www.fotmob.com/terms), proprietary provider data; owner accepts responsibility | Sequential bulk fetch and incremental daily refresh. Lite tier; Understat aggregates enrich overlaps |
| Understat | Public HTML/AJAX JSON **200** | **No** | Normalized shot x/y, provider xG; own xG scored | Rosters, player minutes/positions, provider season/match history incl. PPDA/deep; no shirts/ratings/precise shot clock | Big five + Russia from 2014/15; imported top five 2025/26 and 2026/27; no CL | No open licence found, [site](https://understat.com/); owner responsibility | Existing 2,002 lite exports retained; enrich richer FotMob canonical matches |
| SofaScore | One genuine-browser tournament probe initially **200**, then redirects to **captcha.html** within 30 seconds. Prior JSON403 retained | Not demonstrated | No usable live evidence beyond blocked page | Not independently established from this box | Unverified | Proprietary; owner responsibility | Stop after browser probe. No scraper: no additional full stream established |
| StatsBomb upstream | GitHub/raw **200**; cached upstream commit equals manifest | Yes | Yes; provider xG validation only | Existing events/lineups, some freeze frames | Baseline 2,924 demo matches; upstream `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`, no updates in spike | [Licence](https://github.com/hudl/open-data/blob/master/LICENSE.pdf), attribution terms | Prefer StatsBomb for dated team duplicates |
| Impect open data | GitHub index/sample events/lineups/documentation **200** | Yes, documented both-team coordinates/actions | Yes; provider KPI values separate | Rosters, provider pressure/packing annotations | 306 Bundesliga 2023/24 matches, overlaps Leverkusen StatsBomb | [Licence](https://github.com/ImpectAPI/open-data/blob/main/LICENSE.pdf), research-only restrictions recorded; owner responsibility | Pilot found neutral passes with unobserved receivers and non-spatial foul markers. No full matches published: current binary SPADL outcome mapping would invent information. Raw evidence retained; W14 neutral-outcome handling needed |
| Afriskaut Dynasty | GitHub ZIP **200** | Conditional; strict eligible subset **37**, other 99 incomplete or inconsistent | Yes, own xG | Both-team rosters where present, inferred control runs | Nigeria youth matches 2024-02-27–2024-10-17 | [Apache-2.0](https://github.com/Afriskaut/dynasty-scouting-league-2024-open-data/blob/main/LICENSE) | Retain accepted exports; unvalidated youth-domain transfer |
| football-data.co.uk | CSV/notes **200** | No | No shot coordinates/xG | Results, odds, aggregate stats | Many leagues, 2026/27 reachable | [Data page](https://www.football-data.co.uk/data.php), private-use restrictions; owner responsibility | Result-only fallback; adds no full-stream or shot-map coverage |
| Metrica | GitHub samples **200** | Small both-team event samples, limited action/body-part detail | Shot locations; no own/provider xG yet | Tracking, anonymous players | Three anonymous historical samples | [README](https://github.com/metrica-sports/sample-data), attribution request | Tracking research; low league-match gain |
| SkillCorner | GitHub index/sample **200** | No complete SPADL outcome/contact stream demonstrated | No explicit shots established in sample | Tracking, possessions, dynamic/off-ball phases, physical aggregates | Index 20 A-League 2024/25 matches | [MIT](https://github.com/SkillCorner/opendata/blob/master/LICENSE) | Requires separate contact reconstruction/validation; cannot claim full feature ready |
| OpenFootball | GitHub current EPL **200**, requested recent CL files cached404 | No | No | Scores only | Many leagues/seasons | [CC0](https://github.com/openfootball/football.json/blob/master/LICENSE.md) | Result-only fallback |

## Browser evidence and downloads

`data/sources/browser_round2_report.json` records exact requested URLs, status,
final URL, title and body/HTML/screenshot paths. `data/raw/<source>/browser_probe/`
retains responses and final browser screenshots. WhoScored challenge detection in
the first scratch report missed the “Attention Required” wording; the actual
cached title/HTML and status unambiguously show Cloudflare blocking.

Wyscout `incoming/*.receipt.json` records file URL, suggested filename, bytes,
SHA256 and collection time. Complete archive bytes were fetched once; the first
interrupted browser download resumed its missing bytes using the already cached
redirect. No anti-bot signature or challenge solver was reproduced. The remaining
article 202 does not imply the successful download host was blocked.

## Public AJAX content negotiation

Understat's own `league.min.js` and `match.min.js` call `getLeagueData/<league>/<year>`
and `getMatchData/<id>` through jQuery AJAX. Plain requests returned 404; JSON
requests with jQuery's documented `X-Requested-With: XMLHttpRequest` and
`Accept: application/json` returned 200. These are public representation headers,
not authentication or anti-bot signatures. HTML/plain and AJAX representations
have distinct immutable cache keys; neither cached representation is refetched.
The official shot renderer uses `X*width, (1-Y)*height` for home shots on a
top-left canvas, establishing bottom-left source Y. Our conversion is therefore
`x=X*105, y=Y*68`, with away rotation only at the API boundary.

## Evidence locations

- `data/sources/spike.json` records the initial URLs/statuses/body locations.
- Every `data/raw/<source>/<sha256>.json` has URL, status, fetch time, content type,
  byte count and blocked flag; `.body` retains raw bytes (including error bodies).
- `data/raw/source_host_policy.json` persists refusal state and host timings.
- `data/sources/dynasty_eligibility.json` is the initial coverage-only spike.
  Final accepted IDs are in `catalogue_dynasty.json`; `dynasty_report.json`
  records the stricter parser/clock/score rejections and quarantine moves.
- Actual imported counts and verification are recorded in `LOG.md`.
- OpenFootball's Git tree shows Champions League JSON through 2024/25; probed
  2025/26 and 2026/27 CL URLs return cached 404s. No recent CL coverage is claimed
  from OpenFootball; FotMob supplies the recent Champions League lite coverage.
