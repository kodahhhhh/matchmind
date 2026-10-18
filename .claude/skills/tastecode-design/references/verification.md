# Installation verification — 2026-09-20

TasteCode revision: `3ee7948d8ec9d3f2ac538c7ac9b6c9fa8e345c28`.
Installed cache: `/home/ubuntu/.local/share/tastecode`.

- All 316 catalog image hashes verified; 172 composition groups available, plus the original legacy references and motion source.
- Original design-core suite: 21 files, 147 tests passed. The source-scope extension preserves original behavior when unset.
- Portable runner suite: 7 tests passed. Covers invalid artifacts, phase order, persisted draws, inspection requirements, reference/artifact/screenshot tampering, real project-check failures, stale receipts, four browser captures, enforced target-size repair, motion/reduced-motion probes, review history, and the two-repair limit.
- Eight Node scripts passed syntax checks; skill metadata validation and Git whitespace checks passed.
- AX check planning selected no application checks for this tooling-only change.
- Codex app-server `skills/list` returned `tastecode-design` enabled at the canonical project skill path. OpenCode `debug skill` and Grok `inspect --json` returned the skill. All 17 project compatibility links resolve to that same directory. Other clients were not exercised through authenticated agent sessions.

## Actual visual smoke test

An isolated reading-room fixture supplied a desktop reference. The agent viewed the reference and desktop/mobile screenshots with native image tools. A deliberately shortened button failed both visual review and the automated 44px target check. Restoring its 48px height, rerunning the JavaScript check, recapturing all four viewport/motion variants, and reviewing the pixels produced a passing result after one repair. Focus and disclosure assertions passed. No animation was requested for this fixture; a separate browser test verified real native animation and reduced-motion suppression.

Local evidence, retained outside Git:

- Workspace: `/tmp/tastecode-skill-trF2N4`
- Run: `/tmp/tastecode-skill-trF2N4/.taste/runs/1789945811053-a7a9c584`
- Initial capture: `capture-1789945811114-0`
- Repaired capture: `capture-1789946078858-1`
- Final CLI `finish`: `status=passed`, `repairAttempt=1`, no findings.

The automated runner tests use explicitly synthetic inspection attestations to test state transitions. The separate manual smoke test above supplies actual visual inspection. Neither is an end-to-end model session in every supported agent, nor a Coline UI redesign or production browser test.

Reproduce the helper suite after `setup` with:

```sh
node --test <skill>/scripts/runner.test.mjs
```

The Linux fixture uses `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`. Normal skill runs use the project's approved fonts. Run the original suite from the installed runtime directory with `./node_modules/.bin/vitest run packages/design-agent/src`.
