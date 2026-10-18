# Source and portability

Pinned TasteCode source: https://github.com/Leonxlnx/tastecode/tree/3ee7948d8ec9d3f2ac538c7ac9b6c9fa8e345c28

The external runtime includes every file in `packages/design-agent/src`, all 316 catalog images and 132 legacy direction images, `references/motion/reveal.js`, and original licenses/notices. The catalog contains 172 composition groups, 144 mobile pairs, 10 reviewed groups, and 162 candidates. Candidates require visual inspection. Images remain layout references, not production assets.

Reused directly: qualification and phase prompts; brief/brand/page/assets/review parsers; palette and gradient helpers; typography random draw and selection validation; reference selection/locking; copy and source checks; asset file validation; exact-file validation for new projects; reference and asset hash checks; review findings contract; original DOM audit and settle scripts; original static/command preview implementation and its supporting process/path code.

One marked source patch adds an explicitly enumerated source-file scope to `source-quality.ts`. Without that option, the original implementation and tests retain their behavior. The helper sets the scope only during its own source-validation calls. This keeps the 32 MB source budget meaningful in Coline's larger monorepo.

Portable replacements for TasteCode desktop/server orchestration:

- Atomic per-run files replace TasteCode's SQLite thread payload and single workspace `.taste` artifact directory. Original parsers still validate accepted artifacts; accepted artifact/reference/asset hashes are checked at later stages. Accepted artifact versions and build/repair results remain in the run history.
- A Node CLI emits phase prompts and accepts JSON responses from the existing agent session. It does not create another model session or silently change models.
- A persisted state machine keeps phase order, one asset replan, bounded output corrections, and at most two visual repairs. The helper refuses its own invalid transitions. It cannot stop a general-purpose agent from bypassing it with unrelated tools.
- Native agent image viewing replaces TasteCode's provider adapters. The `inspect` ledger records observations as agent attestations; the CLI cannot prove the model actually viewed pixels.
- Selected reference images are copied into the private run directory for workspace-only image tools. Both originals and local copies remain hash-checked; the full library stays outside the app.
- Playwright Chromium replaces Electron capture. Existing authenticated AX previews are supported. Owned standalone previews are stopped after capture; no desktop preview tab is added.
- Independent browser checks add font/image failure detection, overflow, declared interactions and basic CSS/Web Animations probes. Visual comparison remains model judgment, and browser tests are limited to their actual assertions.
- Existing-app mode explicitly preserves project scope and identity. TasteCode's original new-page defaults remain available in new-page mode. No separate design ideology is layered over it.

Unimplemented desktop features are not part of design judgment: the composer toggle, activity cards, queue/session UI, diff viewer, provider controls and Electron window. Use skill invocation, commentary and saved artifacts instead.

## Agent compatibility

The canonical entry lives in `.agents/skills/tastecode-design`. Codex, OpenCode, Cursor, and installed Grok support that directory. Repository compatibility links expose the same skill under existing vendor skill roots, including Claude and Kiro. A link proves filesystem availability, not authenticated end-to-end execution in every client. For agents without discovery, explicitly read SKILL.md and run its Node CLI.

Use actual native image tools. TasteCode's original Cursor/OpenCode adapters reject images; this skill does not use those adapters. A text-only model still cannot perform reference-driven visual judgment. Report missing image support rather than claiming a path was inspected.

This is repository-wide tooling. User-level agent authentication, models, other projects, and the existing TasteSkill are unchanged. The source and references are cached outside the application, so another machine/worktree runs setup to obtain them.

See [verification.md](verification.md) for the installed revision's tests and client-discovery evidence.
