# Source spike — direct EC2 evidence, 2026-10-05

Each acquisition uses an honest `MatchPulse/0.1 (public football data research)`
User-Agent, a persistent per-host delay of 1.1 seconds, a global acquisition lock,
and immutable raw response caches under `/home/ubuntu/hackathon/data/raw/<source>/`.
403/429/challenges persistently disable that host and source. No cookies, signatures,
proxies, solvers or browser automation were used. Documentation browsing is not
proof of EC2 reachability; the HTTP results below are from this machine.

| Source | Reachable here? | Full events x/y | Shots x/y | Provider xG | Lineups | Ratings | Momentum | Team stats | Coverage / recency | Licence / terms | Effort / decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FotMob public JSON | Yes, `/api/data/leagues` and `/api/data/matchDetails` HTTP 200; legacy `/api/leagues` 404 | **No** in inspected detail | Yes, metre pitch | Yes | Yes, starters + bench | Yes | Yes, proprietary minute series | Yes | Top five + Champions League; league response lists 2026/27 and past seasons; sample finished 2026-09-20 | [Terms](https://www.fotmob.com/terms) prohibit systematic/regular automated use; proprietary provider data, no open licence | Parser for already cached spike; daily/bulk fetching deferred pending provider permission |
| Wyscout Pappalardo / Figshare | **403** at `api.figshare.com/v2/collections/4415000/articles`; stopped | Dataset documents full events | Yes | Not provider xG | Yes | No | Derivable | Derivable | 2017/18 big five, World Cup 2018, Euro 2016; historical | [Collection](https://figshare.com/collections/Soccer_match_event_dataset/4415000), CC BY 4.0; cite Pappalardo et al. | Biggest expected full-stream win; blocked. Offline socceraction adapter possible once owner supplies licensed local files; no alternate mirrors requested after refusal |
| StatsBomb upstream | Yes, GitHub/raw HTTP 200 | Yes | Yes | Yes, validation only | Yes | No | Derivable | Derivable | Upstream `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb` equals `manifest.cloned_commit_sha`; **no updates/new matches** | [Licence](https://github.com/hudl/open-data/blob/master/LICENSE.pdf), custom attribution terms | Already local; no download needed |
| Understat | Yes, HTML and public AJAX JSON HTTP 200 | **No** | Yes, normalized 0–1 | Yes | Yes, roster/position/minutes; no shirt numbers | No | No equivalent VAEP momentum | Season/match aggregates, xG, PPDA etc. | Big five + Russia from 2014/15; 2026/27 reachable; no Champions League | [Site](https://understat.com/), no open data licence found; publication/commercial rights unresolved | Use for private staging shot tier; preserve provider xG separately; own xG transfer needs validation |
| football-data.co.uk | CSV and notes HTTP 200 | No | No | No | No | No | No | Results, aggregate shots/cards/corners + odds | Top five and many other leagues; 2026/27 CSV reachable | [Data page](https://www.football-data.co.uk/data.php) limits use to private individuals and excludes commercial/training products using bots | Do not expand acquisition or publish; owner/provider permission needed |
| SofaScore | **403** on one public JSON test; stopped | Unverified, no full stream established | Unverified | Unverified | Unverified | Unverified | Unverified | Unverified | Not independently measured here | Proprietary, no redistribution rights established | Dropped; no retries |
| Metrica sample data | GitHub README and two event CSVs HTTP 200 | Both-team event samples, 1,745/1,935 rows; limited carry/body-part detail | Yes | No | Anonymized player labels | No | Derivable | Derivable | 3 anonymous historical sample games; not a recent league feed | [Provider README](https://github.com/metrica-sports/sample-data) requests attribution; no standard open licence identified | Useful tracking/model research; small match gain, anonymous teams, commercial rights unclear |
| SkillCorner open data | GitHub README/index/dynamic-event CSV HTTP 200 | **No complete SPADL action/outcome stream demonstrated** | No explicit shot actions in sampled CSV | xshot/derived attributes, not our xG | Match metadata | No | Phases/tracking, not VAEP | Season physical/passing aggregates | Index has **20** A-League 2024/25 matches (README says 10); sampled dynamic CSV includes possession/off-ball/engagement events | [MIT licence](https://github.com/SkillCorner/opendata/blob/master/LICENSE), credit SkillCorner | Separate tracking research; requires an event/ball-contact reconstruction and validation workstream, cannot call full feature ready |
| Impect open data | GitHub index, one event/lineup, licence HTTP 200 | Yes, 2023/24 Bundesliga | Yes | Provider KPIs | Yes | KPI aggregates | pxT, not VAEP | Yes | 306 Bundesliga matches, 2023/24; overlaps Leverkusen's StatsBomb matches | [Licence PDF](https://github.com/ImpectAPI/open-data/blob/main/LICENSE.pdf): analytical/research only, no commercial use, alteration or external redistribution | Sample inspected; excluded from product ingestion pending provider permission |
| Afriskaut Dynasty 2024 | GitHub dataset ZIP/README/event map/licence HTTP 200 | **Conditional**: many one-team or incomplete files; eligibility gate required | Yes | No | Yes where both teams recorded | No | Derivable from accepted action streams | Derivable | 136 Nigeria youth matches in supplied archive; source name 2024, actual dates retained | [Apache-2.0](https://github.com/Afriskaut/dynasty-scouting-league-2024-open-data/blob/main/LICENSE) | Best reachable permissive full-event option found; preserve source annotations, validate clocks/goals/coverage; youth-domain model transfer is unvalidated |
| OpenFootball JSON | GitHub 2026/27 EPL + licence HTTP 200 | No | No | No | No | No | No | Scores only | Many leagues/seasons, current result snapshots | [CC0](https://github.com/openfootball/football.json/blob/master/LICENSE.md) | Safe result-only fallback; does not satisfy shot-map/replay requirements |

## Why acquisition order changes

Wyscout cannot be fetched from this box under the owner's blocking rule. FotMob
is reachable but its terms explicitly exclude the requested daily automation.
No full-event feature can be reconstructed from FotMob shot maps. Therefore:

1. Normalize only the eligible permissively licensed Dynasty streams for full-tier
   research and additional W14 SPADL training files.
2. Use Understat for current/recent big-five shot-tier staging. No CL coverage is
   invented; that remains a provider-permission/source gap.
3. Keep a cached FotMob parser and a contract proposal so the orchestrator can
   adopt it after resolving source permissions.

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
  2025/26 and 2026/27 CL URLs return cached 404s. No recent CL coverage is claimed.
