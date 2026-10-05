# Frontend audit (W15, 2026-10-05)

Walked every screen at 1440×900 and 480×960 against the live API, over the Tailscale IP
(`http://100.97.212.47:5180`, an insecure context) and localhost. Screenshots:
`docs/frontend/screenshots/audit/` (`node scripts/shots.mjs`), flow checks in
`docs/frontend/screenshots/flows/` (`node scripts/flows.mjs`).

The baseline is already good: a consistent dark broadcast look, theme tokens, sentence case,
plain-language glossary, reduced-motion guards, skeletons on most screens. The problems are
about **path, hierarchy and connection**, not polish: the app shows off before it lets a fan
do anything, the match page opens on an empty chat instead of the story, and the advanced
features (cited answers, What-if, moment search) are separate tabs that don't lead into each
other.

## Screens

### Home (`/`)
**Job:** get a fan into a match in one or two taps.

1. **Matches are the last thing on the page.** Hero, stats strip, feature bento, players
   section, *then* the match browser: ~3,000 px down at 1440 and ~6,000 px down at 480.
   "Browse all matches" is a secondary link.
2. **Search can't find a match.** The ⌘K palette searches commentary moments and players,
   not teams or competitions. The team filter in the grid only matches team names and
   resets the competition pills. "Spain v England" or "Champions League" find nothing.
3. **No famous or recent matches up front.** Only the 2022 final is featured. The archive
   has the 2005 Istanbul final, every World Cup final since 2018, Euro and Copa 2024 finals.
4. **Heavy first load.** Home fetches `/matches` (1.05 MB, not gzipped by the API), the
   final's full event stream (850 KB) just to draw the hero pitch, the whole backtest
   (214 KB) for two numbers, plus a leaderboard and 7 player profiles. The JS is one
   1.3 MB chunk (401 KB gzip) including shiki and streamdown, used only by the analyst.
5. **Competition pills are a wall** (17 pills, then 10 season pills) before any match.
6. **Jargon on the landing page:** "Brier score 0.585 vs 0.574", "value added per 90",
   "Hybrid search: Qwen3 embeddings and full text".
7. **Phone:** no nav at all below `md` (Players and Backtest only reachable via the footer).
   The stats strip reels show half-spun digits in screenshots taken mid-animation.

### Match (`/match/:id`)
**Job:** tell the story of the match at a glance, then let you dig into any moment.

1. **Opens on an empty chat.** The right panel defaults to the Analyst with four starter
   cards; the match story (goals, swing, who was on top) is a small list under them, and at
   1440×900 the chat auto-scrolls so the panel header is cut off.
2. **No plain verdict.** Nothing says "Argentina had the better chances but France kept
   coming back". The stats overlay (possession, territory, chances, shots) is hidden on phones.
3. **Features don't connect.** Selecting a moment on the pitch or timeline shows a pill and
   nothing else: no replay, no "ask about this", no "what if". What-if makes you re-find
   the same moment in a chip list. Answers' citations move the pitch, which on a phone is
   1,000 px above the chat, so the tap looks like it did nothing.
4. **Too many controls in the header:** keyboard help, search, play highlights and a large
   violet "Find the turning point" that also fires an LLM question. On a phone they take a
   whole row above the score.
5. **No way back** except the logo.
6. **What if is a wall of chips:** 6 goals, 14 substitutions, 30 shots, all expanded.
7. **Players tab** leads with a "Gap" column ("places higher on impact than on passes")
   that needs explaining; signed VAEP numbers are shown raw in every row.
8. **Moments tab** splits "Most dangerous" (says "VAEP") and "Live commentary"; for matches
   without commentary (e.g. 2005 Istanbul, 1970 final) the feed shimmers "Writing the
   commentary" forever.
9. **Phone timeline:** goal labels stack in two lanes over a 400 px chart; the tab panel is a
   fixed 100 dvh box inside a scrolling page (nested scroll).
10. **Fragile load:** one failing endpoint (players, turning points) fails the whole page.
    W13's "lite" matches (no event stream) would show an error instead of what we have.

### Search palette (⌘K)
**Job:** find any match, player or moment.

1. Matches and competitions aren't searchable (see Home 2).
2. Result rows say nothing about what happens when you open one.
3. Footer copy is model jargon ("Hybrid search: Qwen3 embeddings and full text").
4. ⌘K hint shows on phones, where there's no keyboard.

### Player drawer
Mostly good. "Value added per 90", "Progression per 90", "Expected goals" are unexplained,
and moments in matches outside the replay set are disabled without saying why at a glance.

### Underrated players (`/players`)
Clear question and chart. Metric labels are jargon ("Value added per 90", "Progression per
90"); the scatter's y axis has no plain explanation.

### Market backtest (`/backtest`)
**Job:** answer "would it beat the bookies?" honestly.

The verdict exists but sits under an analyst page: forest plot, two strategy cards,
sensitivity table, player-data table, every bet, 20 caveats, all expanded (7,700 px at 1440).
Units ("u"), Brier scores, CLV and 95% intervals are unexplained.

### 404
Fine.

## Cross-cutting

* **Insecure context:** analyst send works over the Tailscale IP (IDs use a counter, not
  `crypto.randomUUID`). No clipboard or crypto use anywhere. Keep it that way: flows test
  runs against the IP.
* **Accessibility:** focus rings and reduced motion are handled. Gaps: the pitch is one
  `role="img"` with clickable circles that aren't keyboard reachable; tab bar uses
  `aria-pressed` buttons rather than tabs; ⌘K is the only keyboard path to search.
* **Motion:** good overall. Route transitions blur, which is expensive on big pages; the
  stats reel is decorative.

## Ranked plan

1. **Unified search + match-first home.** One search box (matches by team/competition/
   season, players, moments) as the hero; famous and recent matches up front; browse by
   competition below; the showcase sections shrink and move down. Drop the 850 KB hero
   fetch and the backtest fetch from first load. Phone nav menu.
2. **Match page: Story first.** New default "Story" tab: one-line plain verdict, who was on
   top (plain bars), key moments (goals, red cards, biggest swing, best chances) each with
   replay. Highlights and turning point move from the header into the story. Back link.
3. **Connected moments.** Selecting any moment (pitch, timeline, story, answer citation,
   search hit) opens a moment card on the pitch: plain description, replay, "Ask about
   this", "What if" (goals, subs, red cards, shots). What if accepts a picked moment;
   citations scroll the pitch into view on phones.
4. **Graceful sections.** Load match detail first, every other section independently;
   each section hides cleanly when its data is missing (ready for W13 lite matches).
5. **Simplify What if, Players and Moments.** What if: verdict first, goals and red cards
   up front, subs and shots behind disclosures. Players: plain headline, impact bars, raw
   numbers on demand. Moments: one list, empty commentary handled.
6. **Speed.** Code-split routes and the analyst (shiki/streamdown) out of the first chunk;
   share the match list between home and search.
7. **Backtest and leaderboard in plain words.** Short answer first, the analyst-grade
   sections behind "See the numbers" disclosures; plain metric names with Explain tooltips.
8. **Polish pass.** Phone timeline labels, tabs semantics, keyboard reach for moments,
   reduced motion, screenshots of every screen at both sizes.
