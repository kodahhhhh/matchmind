# W15: frontend v2, simpler, easier, more advanced

You're the W15 frontend agent for MatchPulse, a football analytics web app: a match browser, a match page with pitch replay, timeline and momentum, an AI analyst chat with cited answers, moment search, What-if (modelled outcomes), player pages and a market backtest page. The hackathon is over. The owner thinks the tech is genuinely impressive and wants the frontend to be **simpler, easier to use, more advanced and really, really good**: the kind of product a casual football fan opens and immediately gets, and an analyst still finds deep.

You're working in `~/hackathon-W15-frontend` on branch `ws/W15-frontend`. You own `frontend/` only. Read `AGENTS.md` (§6, §8, §11) and `PLAN.md` §8 (design brief) first. `npm ci` has been run.

## What the owner has already told us (follow it)

* **Plain language for casual fans.** Most users don't know what xG, VAEP, field tilt or quantiles mean. Lead every result with a one-line plain verdict. Show probabilities as "% chance of scoring". Say "chances", "territory", "impact", "who's on top". Put raw numbers, ranges and model stats behind a closed "See the numbers" disclosure. Use `src/lib/glossary.ts` + the `Explain` tooltip for any stat label.
* **House style:** sentence case, no em or en dashes in UI copy, Phosphor icons, the `numeral` class for numbers, theme tokens only (no raw hex), team colours from match meta. shadcn + AI Elements are set up (`components.json`, `@/` alias, `src/theme/shadcn.css`).
* **The owner browses at `http://100.97.212.47:<port>` over Tailscale in a ~480 px-wide window. That is NOT a secure context.** Never use secure-context-only APIs (`crypto.randomUUID`, `crypto.subtle`, clipboard without fallback, service workers). A `crypto.randomUUID` call once silently broke the analyst only for the owner while every localhost test passed.
* Counterfactual / What-if output is always labelled as modelled.

## Setup and safety
* Run your dev server on **port 5180**, `--host 0.0.0.0`, proxying `/api` to the live API on `:8000` (read-only use is fine). Use `VITE_USE_FIXTURES=1` where you need to. Don't use :5173/:5174, don't touch main's `frontend/dist`, and don't restart `matchpulse-api`.
* All API access stays in `src/api/client.ts`. If you need an API change, don't make it. Add it to "Requests for other workstreams" in your handoff with the exact shape you want.
* Stop the dev server and any Playwright processes when you finish.

## How to work

1. **Audit first.** Walk every screen at 1440×900 and at 480×960 against the live data (Playwright, against `http://100.97.212.47:5180` as well as localhost). Write `docs/frontend/AUDIT.md`: each screen's job, the top friction points (confusing labels, too many controls, dead ends, slow loads, broken mobile layouts, empty or error states, jargon), and a ranked plan. Use the relevant skills where they help (`better-interface`, `better-layout`, `better-writing`, `dataviz` for charts, `emil-design-eng` / `transitions-polish` for motion, `better-accessibility`).
2. **Then build, in plan order.** Directions the owner cares about:
   * *Simpler:* one obvious path. Find a match (search by team, player or competition; recent and famous matches up front), open it, get the story of the match in one glance, then dig in. Fewer controls on screen at once, clear hierarchy, progressive disclosure.
   * *Easier:* fast first load, skeletons instead of spinners, good empty and error states, keyboard and touch friendly, works one-handed at 480 px.
   * *More advanced:* surface the tech that's already there but buried. Cited analyst answers that jump to the moment on the pitch, What-if, moment search, player impact and the backtest, connected so each one leads naturally into the next (e.g. tap a moment on the timeline → replay it → "ask about this moment" → "what if"). Smooth, purposeful motion; charts that follow the `dataviz` skill.
   * *Super good:* consistent, polished, no layout jank, accessible (focus states, contrast, reduced motion).
3. **Upcoming data tiers:** the W13 agent is adding matches from new sources. Some will be "lite" (score, lineups, shots and stats, but no full event stream, so no replay or VAEP). Watch `~/hackathon-W13-sources/docs/sources/CONTRACT_PROPOSAL.md`. When it appears, make the match page degrade gracefully per section. Until then, build components so a missing section hides cleanly instead of breaking the page.
4. Commit in small steps on `ws/W15-frontend` (don't push or merge). Keep `docs/frontend/LOG.md` updated with what changed and the screenshot paths.

## Verification
`npm run typecheck && npm run lint && npm run build` pass. Playwright screenshots of every changed screen at 1440×900 and 480×960, saved under `docs/frontend/screenshots/` and listed in the LOG. Explicitly check the analyst send flow, What-if and search over the Tailscale IP (insecure context). End with the AGENTS.md handoff.

This is a long effort. Keep working through the plan without stopping for check-ins. If something really needs the owner's call (e.g. removing a whole feature), list it under "Needs owner" at the top of `docs/frontend/LOG.md` and carry on with the rest.
