# Running Design Mode

Use the skill's real absolute path. In this checkout the command is:

```sh
node /home/ubuntu/coline-app/.agents/skills/tastecode-design/scripts/tastecode.mjs doctor
```

`setup` clones or verifies TasteCode revision `3ee7948d8ec9d3f2ac538c7ac9b6c9fa8e345c28`, verifies all 316 reference hashes, copies the complete design core and tests, builds the helper imports, and installs locked dependencies outside the app. Default cache: `~/.local/share/tastecode`. Override with `TASTECODE_DESIGN_HOME`. An existing checkout with another revision or tracked modifications is rejected rather than reset. To retain that checkout, choose another cache directory.

If Chromium is absent, run the installed runtime's `node_modules/.bin/playwright install chromium`. Use the absolute runtime path printed by `doctor`; do not install dependencies into Coline to repair this skill.

## Run configuration

Write the run config under a private temporary directory or `.taste/`. Obtain the actual paths and URL from the task; the following is a structural example, not a command to run against a guessed feature or port.

```json
{
  "workspace": "/absolute/path/to/project",
  "mode": "existing",
  "request": "The user's actual UI request, including scope and constraints",
  "scopes": ["src/components/actual-feature", "src/styles/actual-feature.css"],
  "references": ["/absolute/path/to/current-desktop.png", "/absolute/path/to/current-mobile.png"],
  "checks": [
    {"name":"Relevant project verification","command":"pnpm","args":["run","actual-check-script"],"cwd":"."}
  ]
}
```

Scopes are explicit project-relative files/directories. Include relevant shared components and planned asset destinations. Nonexistent paths can be declared for new files. Exclude unrelated features and generated content. Source quality checks run across these declared scopes and compare with the starting baseline. Pre-existing violations are not silently rewritten. The helper does not monitor arbitrary changes outside those scopes; agent instructions preserve that boundary.

References may be omitted or empty to use the complete bundled selection library. User references take priority and disable random catalog selection, as in TasteCode. `start` captures the baseline before asset acquisition or implementation.

## Phase commands

```sh
node <skill>/scripts/tastecode.mjs start --config <config.json>
node <skill>/scripts/tastecode.mjs prompt --run <returned-run-path>
node <skill>/scripts/tastecode.mjs inspect --run <run> --file <image> --note "Observed composition and responsive relationship"
node <skill>/scripts/tastecode.mjs accept --run <run> --phase brief --file <run>/brief-response.json
```

Read the emitted prompt rather than constructing your own abbreviated workflow. The same pattern repeats for Brand, Page and Assets. A valid brief is an outer object with `status`, `message`, `questions`, and `brief`; later phase schemas are in their prompts.

After implementation:

```sh
node <skill>/scripts/tastecode.mjs check --run <run>
node <skill>/scripts/tastecode.mjs accept --run <run> --phase build --file <run>/build-response.json
```

Check results are executable receipts, not merely strings written by the agent. Changed files invalidate those receipts. Failed checks must be fixed, then rerun. Check logs remain private within the run.

## Existing AX preview

Run `pnpm ax:status` or `pnpm ax:up` as needed and obtain the exact origin. Use the normal `ax:login` fixture state if required. This setup itself does not need to start Coline.

For an existing preview, submit the following shape in the Preview phase with the real URL, selectors and assertions. The example's port is illustrative only.

```json
{
  "version": 1,
  "kind": "existing",
  "url": "http://localhost:12345/actual-route",
  "storageState": ".ax/actual-login-state.json",
  "region": "main",
  "viewports": [
    {"name":"desktop","width":1440,"height":1000},
    {"name":"mobile","width":390,"height":844}
  ],
  "interactions": [
    {"name":"Keyboard focus reaches action","action":"focus","selector":"#actual-action"},
    {"name":"Open details","action":"click","selector":"#actual-action","expect":{"selector":"#actual-details","visible":true}}
  ],
  "motion": []
}
```

Omit `storageState` for public pages. Omit `region` for a whole new page; it scopes interactive-target and image checks, while document heading count and page overflow remain visible. Only loopback HTTP URLs with explicit ports are accepted, including AX's `localhost` origin. The browser may load remote assets but cannot navigate to another origin. Tests should exercise local disposable actions, not send mail or perform live external mutations.

Interaction actions: `click`, `fill`, `press`, `hover`, `focus`, `scroll`. `fill` requires `value`; `press` requires `key`. Except focus/scroll, supply an `expect` with `selector` and at least one of `visible`, `text`, or `attribute: {name,value}`. An interaction listed in the Page plan requires a browser probe. The helper executes probes for desktop/mobile with motion enabled and reduced.

For planned load or scroll entrances, supply probes:

```json
{"motion":[{"sectionId":"hero","selector":"#hero-title","trigger":"load"},{"sectionId":"details","selector":"#details-content","trigger":"scroll"}]}
```

The browser observes CSS/Web Animations on a fresh load and after scrolling, then checks reduced-motion suppression and visibility after rapid scrolling, reload, resize and a reduced-motion change. Probe native CSS/Web Animations this way. Canvas animation and libraries that exclusively write inline styles require additional native browser evidence; do not substitute a false pass. If a different motion mechanism is required, extend the probe implementation or report that coverage blocked.

Font checks require actual loaded FontFace entries for the approved family and weights. Record the actual family used by a framework's generated font CSS in the brand artifact. A CSS declaration falling back to a system font is not a loaded approved face.

For isolated plain HTML projects, the original TasteCode static plan works:

```json
{"version":1,"kind":"static","cwd":".","entry":"index.html","url":"http://127.0.0.1:4173/","viewports":[{"name":"desktop","width":1440,"height":1000},{"name":"mobile","width":390,"height":844}],"interactions":[],"motion":[]}
```

Original command plans also work for non-Coline projects, using the existing declared package script. The helper stops only the preview it starts, after capture. A reused AX server remains running.

## Review and finish

```sh
node <skill>/scripts/tastecode.mjs capture --run <run>
node <skill>/scripts/tastecode.mjs prompt --run <run>
```

Read `browser.json` and inspect the reference and screenshot pixels before submitting Review. All generated automated findings are merged into the review. A repair advances back to capture only after checks and build validation pass. Reuse `status` and `resume` after interruption. `finish` exits 0 only when the review passed and its files/evidence still match; incomplete runs and exhausted repairs exit 2.

Do not modify implementation while a completed screenshot review is being submitted. Use the Repair phase, or start a fresh run if the requested design scope changes. `recapture` refreshes an unchanged Review capture; stale implementation requires a bounded Repair and new check receipts.
