# W15 frontend log

## Needs owner

(none yet)

## 2026-10-05: audit

- Dev server on :5180 (`npx vite --port 5180 --host 0.0.0.0`), proxying `/api` to the live API.
- Added `frontend/scripts/shots.mjs` (every screen at 1440×900 and 480×960, logs console errors and horizontal overflow) and `frontend/scripts/flows.mjs` (analyst send, What-if, search end to end; run against the Tailscale IP).
- Wrote `docs/frontend/AUDIT.md`. Screenshots: `docs/frontend/screenshots/audit/`.
- Baseline flows over `http://100.97.212.47:5180` (insecure context): analyst send PASS on phone and desktop.

## 2026-10-05: build, plan steps 1 to 7

1. **Home + search** (`MatchBrowser`, `MatchGrid`, `SearchPalette`, `store/catalogue.ts`, `lib/matchSearch.ts`):
   search-first hero ("Every match, explained."), famous matches with one-line hooks, latest matches,
   browse by competition with filters in the URL (`/?comp=La Liga&season=…#matches`), top 8 competitions as
   pills plus a "More competitions" select. One search for matches (team, "Spain v England", competition,
   year), competitions, players and moments; stale remote results never flash "nothing found".
   Home no longer fetches the 850 KB event stream or the backtest up front (teaser loads on scroll).
   Phone nav menu in the header.
2. **Match page, Story first** (`StoryPanel`, `lib/story.ts`): plain verdict computed from the data
   (result, whether the chances back it up, territory, the biggest swing, red cards), who was on top bars
   with Explain tooltips, moments that decided it (goals, red cards, swing, big chances) that replay on tap,
   play by play folded away. Tabs are Story · Ask · Players · What if (real tablist, arrow keys).
   Header: back button, search; highlights and "where it turned" moved into the story.
3. **Connected moments** (`MomentCard`, store `showMoment` / `askAbout` / `openWhatIf`): any selected
   moment gets a card (on the pitch on wide screens, under it on phones) with replay, "Ask about this" and
   a what-if when the model supports it. What if runs a handed-over moment straight away. On phones the
   pitch scrolls into view when you pick a moment and the panel scrolls into view when you ask; the camera
   zooms onto the attack being replayed.
4. **Graceful sections**: match detail is the only required call; events, timeline, sequences, players,
   turning points load independently and each section hides when missing. Ready for W13's lite tier
   (`data_tier`, `capabilities`, null possession/momentum): shots-only pitch, chances-only stats, line-ups
   instead of player impact, no What if tab, "Shots & stats" badge on cards. Simulated in `flows.mjs`.
5. **What if / Players**: goals and red cards up front, the six biggest chances (all shots on demand),
   substitutions folded; "Modelled estimate" label, softer analog copy. Players: biggest impact headline,
   impact bars, no "Gap" column.
6. **Speed**: routes and the analyst (markdown + shiki) are separate chunks. Main chunk 1,318 KB → 627 KB
   (401 → 201 KB gzip); analyst 545 KB loads on first Ask. Match chunk prefetched after first paint.
7. **Backtest and leaderboard in plain words**: "Would MatchPulse beat the bookies?", one-sentence short
   answer, "Profit for every 100 staked" chart, stats and strategy rules behind "See the numbers", every
   bet / sensitivity / player data / sources folded (page 7,756 px → 2,527 px at 1440). Leaderboard and
   player drawer: Impact, Chances, Moving the ball forward instead of VAEP-speak.

Flows over `http://100.97.212.47:5180` (insecure context), phone and desktop: analyst send, What if,
moment card → What if hand-off, search "Spain v England" and moments, simulated lite match: all PASS.
