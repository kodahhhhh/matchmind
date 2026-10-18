---
name: sol
description: Delegate code review, root-cause debugging, and deep codebase audits to GPT-6.1 Sol via the Codex CLI, with Claude writing the brief, monitoring the run, and verifying every finding before relaying it. Use when the user asks for Sol, Codex, GPT, or a "second opinion" on code; when a bug's root cause isn't obvious after a first look; before landing a nontrivial or risky change; or for sweeping audits ("find every place that…", "what's wrong with this module").
---

# Sol: GPT-6.1 Sol as an investigator

GPT-6.1 Sol is very good at digging: it reads code paths end to end, keeps pulling on a thread until it finds the problem, and catches regressions other models miss. It's weak at taste, frontend/UI judgment, and long unattended implementation work. So the split is:

- **Sol:** reviews, root-cause hunts, audits, "what touches X and why", checking a plan against the real code.
- **Claude:** writes the brief, runs and monitors Sol, verifies its findings, makes the actual code changes, and talks to the user.

Never ask Sol to implement fixes. If it suggests one, Claude decides whether and how to apply it.

## Running it

Wrapper: `.agents/skills/sol/scripts/sol` (run from the repo root) (model `gpt-6.1-sol`, default effort `high`, full access, no sandbox; sandboxing doesn't work on this machine and the user runs Codex on full access anyway). Every prompt is prefixed with `preamble.md`, which tells Sol to stay read-only and fixes the report format, so the brief only needs task-specific content.

```bash
# Start a run: always with the Bash tool's run_in_background: true. Runs take minutes to tens of minutes.
.agents/skills/sol/scripts/sol run --name auth-race --cd /path/to/repo --prompt-file /path/to/brief.md
# Mid-run progress (recent commands, latest message, tokens)
.agents/skills/sol/scripts/sol status [RUN_DIR]
# Follow-up turn on the same thread (cheap: context is cached)
.agents/skills/sol/scripts/sol resume RUN_DIR --prompt-file /path/to/followup.md
# Recent runs
.agents/skills/sol/scripts/sol list
```

- `--effort`: `high` by default. Use `xhigh` for nasty root causes or large audits, and `max` only when an `xhigh` run came back inconclusive. Don't drop below `high` for reviews.
- Run dirs live in `~/.cache/sol-runs/<timestamp>-<name>/`. `final.N.md` is Sol's report for turn N, and `events.N.jsonl` is the full trace (every command it ran and its output), useful for checking how it reached a claim.
- Write briefs to the scratchpad directory, not the repo.
- When the run finishes, the background task notification includes the summary and the final report. Don't poll in a loop. Check `status` only if the user asks for progress or a run has gone unusually long (>30 min).
- If the summary prints `WARNING: the worktree changed`, check whether Sol edited files (compare with your own and the user's activity) and tell the user before anything else. Don't revert on your own.

## Writing the brief

Sol starts cold, so the brief carries everything it needs. Include:

1. **Goal:** the specific question ("why does X happen", "review this diff for correctness and regressions").
2. **Scope:** the diff range (`git diff main...HEAD`, a commit, uncommitted changes), files or directories, and what's out of scope.
3. **Context you already have:** symptoms, repro steps, error text, logs, relevant files, recent related commits, constraints from the user.
4. **What's ruled out:** label it "already checked", with the evidence, so Sol doesn't redo it. Label your own guesses as unverified hypotheses.
5. **Done means:** for example, "root cause traced to a specific line with a concrete trigger", or "every finding has a failure scenario".

**Avoid anchoring on reviews.** Describe what the change is supposed to do, but don't tell Sol which parts you think are fine or what you expect it to find. An independent read is the whole point.

## Patterns

- **Pre-land review:** after finishing a nontrivial change and before committing, run a Sol review of the diff in the background while you do your own self-check. Merge both result sets.
- **Root cause:** give Sol the symptom and repro, ask for the causal chain, and ask for a test or command that demonstrates it. Ask for the fix only as a suggestion.
- **Fan-out audit:** for large sweeps, split by area (package, layer, concern) and launch 2–4 runs in parallel, each with a tight scope. Use distinct `--name`s.
- **Double-blind:** for high-stakes changes, run two independent reviews with the same brief and compare. Findings both runs agree on are strong; findings only one run reports need closer checking.
- **Pushback:** if a finding looks wrong, `resume` and challenge it with your evidence. Sol will defend it with a trace or retract it. This is cheap because the context is cached.
- **Verify a fix:** after you fix something Sol found, `resume` the same run and ask it to re-check the fix and look for anything the fix broke.

## Verifying before relaying

Sol is a strong signal, not ground truth. For every finding:

1. Open the cited `path:line` and read the surrounding code yourself.
2. Confirm the failure scenario is reachable. Run the test or repro it gave if that's cheap.
3. Classify the finding as **confirmed** (you verified it), **plausible** (consistent with the code but not verified), or **rejected** (wrong, with a one-line reason).

Tell the user what was confirmed, with your own explanation and Sol's evidence. Mention plausible findings as such, and drop rejected ones unless the rejection is itself informative. Say that a finding came from Sol when that's useful. Never pass on raw Sol output as verified.

## When not to use Sol

- UI, visual design, copy, and anything taste-driven.
- Writing or refactoring code.
- Trivial questions you can answer faster yourself by reading one file.
