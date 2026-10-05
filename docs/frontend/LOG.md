# W15 frontend log

## Needs owner

(none yet)

## 2026-10-05: audit

- Dev server on :5180 (`npx vite --port 5180 --host 0.0.0.0`), proxying `/api` to the live API.
- Added `frontend/scripts/shots.mjs` (every screen at 1440×900 and 480×960, logs console errors and horizontal overflow) and `frontend/scripts/flows.mjs` (analyst send, What-if, search end to end; run against the Tailscale IP).
- Wrote `docs/frontend/AUDIT.md`. Screenshots: `docs/frontend/screenshots/audit/`.
- Baseline flows over `http://100.97.212.47:5180` (insecure context): analyst send PASS on phone and desktop.
