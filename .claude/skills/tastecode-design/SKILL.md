---
name: tastecode-design
description: Run TasteCode Design Mode when the user asks for TasteCode, design mode, or its reference-driven design workflow while building or redesigning Coline UI. Uses the original phase prompts, image library, validated artifacts, browser review and bounded repairs in the current agent session.
license: Apache-2.0; preserve the original reference library notices.
---

# TasteCode Design Mode

Begin this workflow when the user asks to use TasteCode Design Mode. Use your current session and chosen model. This skill is for agents building Coline. It does not add a feature to the Coline application.

The original design engine and all reference images are installed outside the application. The scripts in this skill provide reproducible setup and portable orchestration. Read [usage.md](references/usage.md) for command and configuration examples. Read [adaptations.md](references/adaptations.md) when you need exact differences from TasteCode or an agent cannot inspect images.

## Run the workflow

1. Resolve this skill's real directory. Run `node <skill>/scripts/tastecode.mjs doctor`. If setup is absent or outdated, run `setup`, then `doctor`. Do not install TasteCode desktop or change agent authentication/model settings.
2. Inspect the relevant repository instructions and existing UI. Prepare a run config with the user's request, exact source scopes, relevant executable checks, and existing references. Use `existing` mode for edits to Coline; preserve its components, identity and scope. Use `new-page` only for a new deliverable. Prefer actual current-page screenshots as references when preserving an existing layout. The bundled library supplies composition references when none are provided.
3. Run `start --config <file>`. All responses, artifacts and screenshots belong in its private run directory under `.taste/runs/`.
4. Run `prompt --run <run>`, read the emitted prompt file completely, and perform that phase. These are the original TasteCode instructions, not a summarized taste checklist. Inspect every listed reference image using your native image tool. For each image, record an actual observation with `inspect`. A filename or textual description is not visual inspection. If the current agent/model cannot view pixels, report that limitation and stop the visual workflow.
5. Write the requested JSON response inside the run directory. Submit it with `accept --run <run> --phase <current-phase> --file <response>`. If rejected, read the correction prompt and correct the cause. The runner enforces retry budgets. Continue through Brief → Brand → Page → Assets → Build. Asset acquisition may return to Page once. Do not bypass a failed phase, rewrite accepted artifacts, or reroll the saved reference/font draw.
6. During Build and each Repair, run `check --run <run>` after the last edit. It executes the configured project checks and ties the results to the current files. Include all created/changed files within the run's scope in the Build/Repair result, including files acquired in Assets. Preserve unrelated user changes. For Coline, consult `pnpm ax:verify --changed --plan` and run applicable design/domain checks; select the appropriate closure, not a token syntax check.
7. Accept a Preview plan, then run `capture`. For Coline, reuse AX's exact origins and fixture login state. Do not guess ports or start a second application server. The helper captures desktop/mobile and reduced-motion variants, audits the rendered page, tests declared interactions, and saves evidence. It starts/stops an owned preview only for standalone fixtures or other projects.
8. Read the Review prompt. View every output screenshot and selected reference. Compare geometry, typography, imagery and responsive composition. Read the browser evidence too. Submit an honest review. Automated findings are merged even if the model requests a pass. If Repair is selected, fix those findings, run checks, accept Repair, recapture, and review again. At most two visual repair passes are allowed.
9. Run `finish`. Report the result, evidence paths, any remaining findings, and any checks that could not run. Exit code 0 means the validated review passed; exhausted repairs and incomplete runs are not passes.

## Preserve the contract

- Keep your normal concise progress updates in chat. JSON-only phase instructions apply to the response files submitted to the helper, not all user communication.
- Use the user's scope and repository rules before TasteCode's default design choices. Existing-app edits do not authorize new sections, replacement typefaces, new animations, or a whole-app redesign. Existing brand decisions are locked in Brief/Brand.
- Do not automatically combine this workflow with TasteSkill or other design-direction skills. They remain available separately. Ordinary repository checks and image/browser tools are still used.
- References are composition guidance, not production imagery. Acquire real assets through available tools and retain provenance. Keep the full original notices with the external library.
- An `inspect` record is an agent's assertion that it viewed pixels, not proof from the helper. Still screenshots cannot prove interaction or motion. Run the declared browser probes and report untested behavior honestly.
- Resume with `resume --run <run>`. Reference hashes, accepted artifacts, check receipts and screenshot evidence must still match. Never delete a lock without checking whether another command is active.

## Agent entry points

Codex: `$tastecode-design`. Grok, Cursor, Claude and other slash-skill clients: `/tastecode-design` where supported. OpenCode and any other agent: ask to use `tastecode-design`, or explicitly read this file and run the same Node CLI. Compatibility links point to this one skill; there are no separate prompt copies to drift.
