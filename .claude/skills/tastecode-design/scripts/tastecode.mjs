#!/usr/bin/env node
import { readFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
import { installation, modules, runtime, setup } from './bootstrap.mjs';
import { locked, readJSON } from './files.mjs';
import * as runner from './runner.mjs';

const { values: args, positionals } = parseArgs({ allowPositionals: true, options: {
  run: { type: 'string' }, config: { type: 'string' }, phase: { type: 'string' }, file: { type: 'string' }, note: { type: 'string' },
} });
const [command = 'help'] = positionals;
try {
  let result;
  if (command === 'help') result = {
    usage: 'node <skill>/scripts/tastecode.mjs <command> [options]',
    commands: {
      setup: 'Extract pinned TasteCode source and install its isolated runtime',
      doctor: 'Verify the installed runtime and Chromium availability',
      start: '--config run-config.json',
      status: '--run absolute-run-directory',
      prompt: '--run ... (read the emitted prompt file and inspect the listed images)',
      inspect: '--run ... --file image.png --note "Concrete observation after native image inspection"',
      accept: '--run ... --phase brief|brand|page|assets|build|preview|review|repair --file response.json',
      check: '--run ... (executes the configured project checks)',
      capture: '--run ... (real browser capture and objective checks)',
      recapture: '--run ... (new browser evidence without replacing a review with stale screenshots)',
      resume: '--run ... (validates saved artifacts and emits the current prompt)',
      finish: '--run ... (only exits successfully for an evidenced passing review)',
    },
  };
  else if (command === 'setup') result = await setup();
  else if (command === 'doctor') {
    const m = await modules();
    const browser = await m.playwright.chromium.launch({ headless: true, args: ['--no-sandbox'] });
    await browser.close();
    result = { ...installation(), chromium: 'launch passed', imageInspection: 'Use the current agent\'s native image tool; this command cannot verify model vision.' };
  } else {
    const m = await modules();
    if (command === 'start') result = runner.start(readJSON(args.config), m.core);
    else {
      if (!args.run) throw new Error('--run is required');
      result = await locked(args.run, async () => {
        const s = runner.load(args.run);
        if (command === 'status') return runner.summary(s);
        if (command === 'prompt' || command === 'resume') return runner.prompt(s, m.core);
        if (command === 'inspect') return runner.inspect(s, m.core, args.file, args.note);
        if (command === 'accept') return runner.accept(s, m.core, args.phase, readFileSync(args.file, 'utf8'));
        if (command === 'check') return runner.check(s, m.core);
        if (command === 'capture' || command === 'recapture') return runner.captureRun(s, m, command === 'recapture');
        if (command === 'finish') {
          runner.validate(s, m.core);
          if (s.status !== 'passed') process.exitCode = 2;
          return runner.summary(s);
        }
        throw new Error(`Unknown command: ${command}`);
      });
    }
  }
  if (result?.passed === false || ['failed', 'findings-remain'].includes(result?.status)) process.exitCode = 2;
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
} catch (error) {
  process.stderr.write(JSON.stringify({ error: error.message, runtime }) + '\n');
  process.exitCode = 1;
}
