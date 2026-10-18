import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { modules } from './bootstrap.mjs';
import { capture } from './browser.mjs';
import * as r from './runner.mjs';
import * as f from './fixtures.mjs';

const m = await modules();
async function reference(workspace) {
  const p = await m.preview.startDesignPreview(workspace, m.core.parsePreviewPlan(f.preview));
  const browser = await m.playwright.chromium.launch({ args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await page.goto(p.url); await page.evaluate(() => document.fonts.ready);
    const file = path.join(workspace, '.taste', 'test-reference.png');
    await page.screenshot({ path: file });
    return file;
  } finally { await browser.close(); await p.stop(); }
}
async function acknowledge(s) {
  // Synthetic test input, not claimed as actual model inspection.
  for (const image of r.prompt(s, m.core).images) r.inspect(s, m.core, image, 'Synthetic inspection attestation for runner validation test only');
}
async function advance(s, phase, value) {
  await acknowledge(s);
  await r.accept(s, m.core, phase, JSON.stringify(value));
}
async function planned() {
  const workspace = f.fixture();
  const ref = await reference(workspace);
  const s = r.load(r.start(f.config(workspace, [ref]), m.core).run);
  await advance(s, 'brief', f.brief);
  await advance(s, 'brand', f.brand);
  await advance(s, 'page', f.page);
  await advance(s, 'assets', f.assets);
  return s;
}
test('reject invalid artifacts and phase skipping, preserving resumable phase', async () => {
  const workspace = f.fixture();
  const s = r.load(r.start(f.config(workspace), m.core).run);
  await assert.rejects(r.accept(s, m.core, 'build', '{}'), /Expected brief/);
  await assert.rejects(r.accept(s, m.core, 'brief', '{}'));
  assert.equal(r.load(s.run).phase, 'brief');
  assert.equal(r.load(s.run).status, 'running');
  await r.accept(s, m.core, 'brief', JSON.stringify(f.brief));
  const restored = r.load(s.run);
  assert.deepEqual(restored.deck, s.deck);
  assert.deepEqual(restored.typography, s.typography);
  assert.match(r.prompt(restored, m.core).prompt, /brand.prompt.md$/);
  await assert.rejects(r.accept(restored, m.core, 'brand', JSON.stringify(f.brand)), /Inspect and record/);
  writeFileSync(path.join(s.run, 'brief.json'), '{}');
  assert.throws(() => r.validate(s, m.core), /changed/);
});
test('repeated invalid output stops the flow', async () => {
  const s = r.load(r.start(f.config(f.fixture()), m.core).run);
  await assert.rejects(r.accept(s, m.core, 'brief', '{}'));
  await assert.rejects(r.accept(s, m.core, 'brief', '{}'));
  assert.equal(r.load(s.run).status, 'failed');
});
test('reference hashes prevent resume after reference replacement', async () => {
  const workspace = f.fixture();
  const file = await reference(workspace);
  const s = r.load(r.start(f.config(workspace, [file]), m.core).run);
  writeFileSync(file, 'changed');
  assert.throws(() => r.validate(s, m.core), /changed/);
});
test('project checks must run and fail when syntax breaks; stale receipts cannot pass build', async () => {
  const s = await planned();
  await acknowledge(s);
  await assert.rejects(r.accept(s, m.core, 'build', JSON.stringify(f.build)), /Run check/);
  writeFileSync(path.join(s.workspace, 'script.js'), 'const = broken');
  assert.equal((await r.check(s, m.core)).passed, false);
  assert.equal(r.load(s.run).phase, 'build');
  writeFileSync(path.join(s.workspace, 'script.js'), 'console.log("fixture")');
  assert.equal((await r.check(s, m.core)).passed, true);
  writeFileSync(path.join(s.workspace, 'style.css'), f.css(true));
  await assert.rejects(r.accept(s, m.core, 'build', JSON.stringify(f.build)), /Run check/);
});
test('real screenshots force repair of undersized targets, then accept a recaptured repair', async () => {
  const s = await planned();
  writeFileSync(path.join(s.workspace, 'style.css'), f.css(true));
  assert.equal((await r.check(s, m.core)).passed, true);
  await advance(s, 'build', f.build);
  await advance(s, 'preview', f.preview);
  const capture = await r.captureRun(s, m);
  assert.equal(capture.screenshots.length, 4);
  assert.ok(capture.findings.some(x => x.id.startsWith('interactive_target_size')));
  assert.ok(s.capture.evidence.every(e => e.actionResults.every(a => a.passed)));
  assert.ok(s.capture.evidence.every(e => e.readiness.missingFonts.length === 0));
  await advance(s, 'review', f.passingReview);
  assert.equal(s.phase, 'repair');
  assert.equal(s.repairAttempt, 1);
  writeFileSync(path.join(s.workspace, 'style.css'), f.css());
  assert.equal((await r.check(s, m.core)).passed, true);
  await advance(s, 'repair', { ...f.build, files: ['style.css'] });
  await r.captureRun(s, m);
  assert.deepEqual(s.capture.findings, []);
  await advance(s, 'review', f.passingReview);
  assert.equal(s.status, 'passed');
  const reviews = s.history.filter(entry => entry.artifact === 'review');
  assert.deepEqual(reviews.map(entry => entry.value.verdict), ['repair', 'pass']);
  assert.ok(reviews[0].value.findings.length > 0);
  r.validate(s, m.core);
  const shot = s.capture.screenshots[0];
  const bytes = readFileSync(shot.path);
  writeFileSync(shot.path, Buffer.concat([bytes, Buffer.from('tamper')]));
  assert.throws(() => r.validate(s, m.core), /Screenshot changed/);
});
test('browser checks detect real motion and reduced-motion suppression', async () => {
  const workspace = f.fixture();
  const html = path.join(workspace, 'index.html');
  writeFileSync(html, readFileSync(html, 'utf8').replace('<h1>', '<h1 id="heading">'));
  writeFileSync(path.join(workspace, 'style.css'), f.css() + '\n@keyframes entrance{from{transform:translateY(16px)}to{transform:translateY(0)}}#heading{animation:entrance .6s ease-out}@media(prefers-reduced-motion:reduce){#heading{animation:none}}');
  const state = { workspace, approved: { brand: f.brand }, preview: { ...f.preview, motion: [{ sectionId: 'reading', selector: '#heading', trigger: 'load' }] } };
  const result = await capture(state, m, path.join(workspace, '.taste', 'motion-proof'));
  assert.deepEqual(result.findings, []);
  assert.ok(result.evidence.every(e => e.motionResults.length === 1 && e.motionResults[0].passed));
  writeFileSync(path.join(workspace, 'style.css'), f.css());
  const missing = await capture(state, m, path.join(workspace, '.taste', 'missing-motion'));
  assert.ok(missing.findings.some(finding => finding.id.startsWith('motion_')));
});
test('repair limit and stale capture transitions survive process reload', async () => {
  const s = await planned();
  await r.check(s, m.core);
  await advance(s, 'build', f.build);
  await advance(s, 'preview', f.preview);
  await r.captureRun(s, m);
  writeFileSync(path.join(s.workspace, 'style.css'), f.css(true));
  assert.throws(() => r.validate(s, m.core), /Source changed/);
  const transitioned = await r.captureRun(s, m, true);
  assert.equal(transitioned.phase, 'repair');
  assert.equal(r.load(s.run).repairAttempt, 1);
  await r.check(s, m.core);
  await advance(s, 'repair', { ...f.build, files: ['style.css'] });
  await r.captureRun(s, m);
  await advance(s, 'review', f.passingReview);
  assert.equal(s.repairAttempt, 2);
  await r.check(s, m.core);
  await advance(s, 'repair', f.build);
  await r.captureRun(s, m);
  await advance(s, 'review', f.passingReview);
  assert.equal(s.status, 'findings-remain');
  assert.equal(s.phase, 'complete');
  assert.equal(s.repairAttempt, 2);
});
