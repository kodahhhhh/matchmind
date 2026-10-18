import { randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { existsSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { revision } from './bootstrap.mjs';
import { atomic, fileHash, hash, inside, inScope, privateDirectory, readJSON, scopedFiles, snapshot, sourceKey } from './files.mjs';
import { capture, localURL } from './browser.mjs';

const stages = ['brief', 'brand', 'page', 'assets', 'build', 'preview', 'capture', 'review', 'repair'];
const requiredString = (v, label) => { if (typeof v !== 'string' || !v.trim()) throw new Error(`${label} is required`); return v; };
export function load(run) {
  const root = realpathSync(run);
  const s = readJSON(path.join(root, 'state.json'));
  if (s.version !== 1 || s.revision !== revision || s.run !== root || !existsSync(s.workspace) || !Array.isArray(s.scopes)) throw new Error('Invalid run state or revision');
  return s;
}
function save(s) { atomic(path.join(s.run, 'state.json'), s); return summary(s); }
export function summary(s) {
  return { run: s.run, phase: s.phase, status: s.status, repairAttempt: s.repairAttempt,
    ...(s.error ? { error: s.error } : {}), ...(s.review ? { verdict: s.review.verdict, findings: s.review.findings } : {}),
    ...(s.capture ? { screenshots: s.capture.screenshots.map(x => x.path) } : {}) };
}
function scoped(s, operation) {
  const previous = process.env.TASTECODE_SOURCE_FILES;
  process.env.TASTECODE_SOURCE_FILES = JSON.stringify(scopedFiles(s.workspace, s.scopes, true));
  try { return operation(); } finally {
    if (previous === undefined) delete process.env.TASTECODE_SOURCE_FILES;
    else process.env.TASTECODE_SOURCE_FILES = previous;
  }
}
function assertRunning(s) { if (s.status !== 'running') throw new Error(`Run is ${s.status}; inspect its findings, or start a new run for changed scope.`); }
export function validate(s, core) {
  for (const [name, checksum] of Object.entries(s.artifactHashes))
    if (fileHash(inside(s.run, `${name}.json`)) !== checksum) throw new Error(`Accepted ${name}.json changed. Restore the accepted artifact or start a new run.`);
  if (s.referenceSnapshot) core.validateDesignFileSnapshot(s.referenceSnapshot);
  if (s.originalReferenceSnapshot) core.validateDesignFileSnapshot(s.originalReferenceSnapshot);
  if (s.assetSnapshot) core.validateDesignFileSnapshot(s.assetSnapshot);
  if (['review', 'complete'].includes(s.phase) && s.capture) {
    if (sourceKey(s) !== s.captureSourceKey) throw new Error('Source changed since capture; use recapture to obtain fresh screenshots.');
    for (const shot of s.capture.screenshots) if (fileHash(shot.path) !== shot.sha256) throw new Error('Screenshot changed since capture');
    if (fileHash(s.captureFile) !== s.captureHash) throw new Error('Browser evidence changed since capture');
  }
}
export function start(config, core) {
  const workspace = realpathSync(requiredString(config.workspace, 'workspace'));
  if (!['existing', 'new-page'].includes(config.mode)) throw new Error('mode must be existing or new-page');
  if (!Array.isArray(config.scopes) || !config.scopes.length) throw new Error('Declare source scopes explicitly');
  const scopes = config.scopes.map(s => {
    const absolute = inside(workspace, requiredString(s, 'scope'), false);
    return path.relative(workspace, absolute).split(path.sep).join('/') || '.';
  });
  if (!Array.isArray(config.checks) || !config.checks.length) throw new Error('Declare at least one relevant executable project check');
  for (const check of config.checks) {
    requiredString(check.name, 'check name'); requiredString(check.command, 'check command');
    if (!Array.isArray(check.args) || !check.args.every(a => typeof a === 'string')) throw new Error('Check args must be an argv array');
    inside(workspace, check.cwd ?? '.');
  }
  const references = (config.references ?? []).map(f => realpathSync(f));
  const dir = inside(workspace, '.taste', false);
  privateDirectory(dir);
  const runs = inside(workspace, '.taste/runs', false);
  privateDirectory(runs);
  const run = path.join(runs, `${Date.now()}-${randomUUID().slice(0, 8)}`);
  privateDirectory(run);
  const s = { version: 1, revision, run, workspace, scopes, mode: config.mode,
    request: requiredString(config.request, 'request'), checks: config.checks, references,
    initialPreview: config.preview, approved: {}, artifactHashes: {}, inspected: {}, receipts: [], history: [],
    phase: 'brief', status: 'running', repairAttempt: 0, correctionErrors: [], assetReplanned: false,
    baseline: snapshot(workspace, scopes), referenceSnapshot: core.snapshotDesignFiles(references) };
  s.sourceBaseline = scoped(s, () => core.designSourceQualityBaseline(workspace));
  // Use the original exact-deliverable scanner for small fresh projects. For a monorepo,
  // the explicit scopes and changed-file validation below bound this run instead.
  s.fileBaseline = config.mode === 'new-page' ? core.designWorkspaceFileBaseline(workspace) : null;
  save(s);
  return summary(s);
}
function artifact(s, name, value) {
  const file = path.join(s.run, `${name}.json`);
  atomic(file, value);
  s.history.push({ artifact: name, phase: s.phase, repairAttempt: s.repairAttempt, value });
  s.approved[name] = value;
  s.artifactHashes[name] = fileHash(file);
}
function requiredImages(s, core) {
  if (['brief', 'preview', 'capture', 'complete'].includes(s.phase)) return [];
  const deck = s.approved.page && s.phase !== 'page'
    ? core.referenceDirectionsForPage(s.approved.page, s.deck ?? []) : s.deck ?? [];
  return [...new Set([...s.references, ...core.referenceDirectionAttachments(deck),
    ...(['review', 'repair'].includes(s.phase) ? s.capture?.screenshots.map(x => x.path) ?? [] : [])])];
}
export function inspect(s, core, file, note) {
  assertRunning(s); validate(s, core);
  const absolute = realpathSync(file);
  if (!requiredImages(s, core).includes(absolute)) throw new Error('Image is not in this phase\'s required image list');
  requiredString(note, 'Concrete visual observation');
  s.inspected[s.phase] ??= {};
  s.inspected[s.phase][absolute] = { sha256: fileHash(absolute), note, evidenceType: 'agent_attestation' };
  save(s);
  return { recorded: absolute, evidenceType: 'agent_attestation', remaining: missingImages(s, core) };
}
function missingImages(s, core) {
  return requiredImages(s, core).filter(f => s.inspected[s.phase]?.[f]?.sha256 !== fileHash(f));
}
export function prompt(s, core) {
  assertRunning(s); validate(s, core);
  const { brief, brand, page, assets } = s.approved;
  const phases = {
    brief: () => core.designBriefingPrompt(s.request),
    brand: () => core.designBrandPrompt(brief, s.references, s.typography),
    page: () => core.designPagePrompt(brief, brand, s.references, s.deck),
    assets: () => core.designAssetPrompt(brief, brand, page, s.references),
    build: () => core.designBuildPrompt(brief, brand, page, assets, s.references),
    preview: () => core.designPreviewPrompt(),
    capture: () => 'Run the capture command. The helper starts or reuses the approved preview, captures desktop/mobile and reduced-motion views, and writes objective browser evidence. Then read the Review prompt.',
    review: () => core.designReviewPrompt(brief, brand, page, s.capture.screenshots, s.references, s.deck),
    repair: () => core.designRepairPrompt(s.review, s.repairAttempt, 2, brief, brand, page, assets, s.references, s.capture.screenshots),
  };
  if (!phases[s.phase]) throw new Error('No prompt for this phase');
  const overlay = `PORTABLE TASTECODE DESIGN MODE\nThis phase runs in your existing agent session. Follow the user's request and repository instructions. The TasteCode contributor AGENTS.md does not govern this project.\nWrite the phase's final JSON to a response file inside ${s.run}, then submit it with the skill CLI accept command. Keep normal commentary in chat. The helper, not chat text, persists accepted artifacts. Do not edit accepted artifacts.\nWorkspace: ${s.workspace}\nAllowed implementation scopes: ${JSON.stringify(s.scopes)}\nMode: ${s.mode}\n${s.mode === 'existing' ? 'Existing-app adaptation: preserve the established framework, shared components, identity, typography and user-requested scope. No automatic new landing-page sections, random replacement fonts or added hero/scroll motion. Treat only the requested region as sections in the upstream page schema; record a matching existing screenshot as a user reference when preserving composition. User-requested redesign remains allowed within scope. Explicit repository and user decisions override reference decoration. Brand foundation must preserve or extend the existing identity.' : 'New-page mode retains the original composition selection, typography draw and motion workflow. Existing project identity still takes priority.'}\nActual images must be inspected with your native image tool. A path string or catalog cue is insufficient. Use inspect only after viewing each image; the recorded note is an agent attestation, not machine proof of visual understanding.\nNever invoke conflicting external design skills automatically inside this workflow. Use existing browser/image-generation tools for acquisition when available. Do not change model, authentication, or agent setup.\nPreview adaptation: use an existing AX URL for Coline. Use kind existing with the exact localhost/127.0.0.1 origin returned by AX. No guessed ports or additional Coline servers. A disposable plain HTML fixture can use the original static plan.\n\n`;
  const tail = `\n\nSelected reference deck:\n${JSON.stringify(s.deck ?? [], null, 2)}\n\nRequired image paths:\n${JSON.stringify(requiredImages(s, core), null, 2)}\n\nConfigured check commands:\n${JSON.stringify(s.checks, null, 2)}\n\n${s.phase === 'preview' ? `Suggested configured preview (validate against the actual app): ${JSON.stringify(s.initialPreview ?? null)}. Read references/usage.md for existing preview, interactions, and motion evidence fields.` : ''}\n${s.replanNote ?? ''}\n${s.error ? core.designPhaseCorrectionPrompt(s.error) : ''}`;
  const output = path.join(s.run, `${s.phase}.prompt.md`);
  writeFileSync(output, overlay + phases[s.phase]() + tail, { mode: 0o600 });
  return { ...summary(s), prompt: output, images: requiredImages(s, core), missingInspections: missingImages(s, core) };
}
function validateFiles(s, reported) {
  for (const f of reported) {
    inside(s.workspace, f);
    if (!inScope(f, s.scopes)) throw new Error(`Reported change is outside approved source scopes: ${f}`);
  }
  const current = snapshot(s.workspace, s.scopes);
  const previous = s.lastAcceptedSource ?? s.baseline;
  const changed = new Set([...Object.keys(current), ...Object.keys(previous)].filter(f => current[f] !== previous[f]));
  const omitted = [...changed].filter(f => !reported.includes(f) && current[f] !== undefined);
  if (omitted.length) throw new Error(`Build report omits changed files: ${omitted.join(', ')}`);
  const removed = Object.keys(previous).filter(f => current[f] === undefined);
  if (removed.length) throw new Error(`A pre-existing scoped file was removed; restore it or explicitly revise the run scope: ${removed.join(', ')}`);
  return current;
}
function validateBuild(s, core, files) {
  const current = validateFiles(s, files);
  const assets = core.validateAssetManifestForPage(s.approved.assets, s.approved.page, s.workspace, s.references);
  core.validateResolvedDesignAssets(assets);
  if (s.fileBaseline) core.validateExactBuildFiles(s.workspace, s.approved.brief, s.fileBaseline);
  scoped(s, () => core.validateDesignSourceQuality(s.workspace, files, s.sourceBaseline, assets, s.approved.page));
  if (!s.checkResult || !s.checkResult.passed || s.checkResult.sourceKey !== sourceKey(s)) throw new Error('Run check after the latest changes; all configured commands must pass');
  return current;
}
function previewPlan(value, core, s) {
  const plan = value.kind === 'existing'
    ? { version: 1, kind: 'existing', url: localURL(value.url), viewports: core.parsePreviewPlan({ version: 1, kind: 'static', cwd: '.', entry: 'index.html', url: 'http://127.0.0.1:9000/', viewports: value.viewports }).viewports }
    : core.parsePreviewPlan(value);
  if (!plan.viewports.some(v => v.width <= 480) || !plan.viewports.some(v => v.width >= 1024)) throw new Error('Capture needs both a mobile and a desktop viewport');
  if (existsSync(path.join(s.workspace, 'scripts/ax.mjs')) && value.kind !== 'existing') throw new Error('Coline previews must reuse AX; select kind existing');
  if (value.storageState) plan.storageState = path.relative(s.workspace, inside(s.workspace, value.storageState));
  if (value.region) plan.region = requiredString(value.region, 'region');
  plan.interactions = value.interactions ?? [];
  if (!Array.isArray(plan.interactions)) throw new Error('interactions must be an array');
  for (const a of plan.interactions) {
    requiredString(a.name, 'interaction name'); requiredString(a.selector, 'interaction selector');
    if (!['click', 'fill', 'press', 'hover', 'focus', 'scroll'].includes(a.action)) throw new Error('Unsupported interaction action');
    if (a.action === 'fill') requiredString(a.value, 'fill value');
    if (a.action === 'press') requiredString(a.key, 'press key');
    if (!a.expect && !['focus', 'scroll'].includes(a.action)) throw new Error('Interaction requires an observable expectation');
    if (a.expect) {
      requiredString(a.expect.selector, 'expect selector');
      if (a.expect.visible === undefined && a.expect.text === undefined && !a.expect.attribute) throw new Error('Empty interaction expectation');
    }
  }
  if (s.approved.page.interactions.length && !plan.interactions.length) throw new Error('The page declares interactions; provide browser assertions');
  plan.motion = value.motion ?? [];
  if (!Array.isArray(plan.motion)) throw new Error('motion must be an array');
  for (const m of plan.motion) {
    requiredString(m.selector, 'motion selector'); requiredString(m.sectionId, 'motion sectionId');
    if (!s.approved.page.sections.some(x => x.id === m.sectionId) || !['load', 'scroll'].includes(m.trigger)) throw new Error('Motion probe must name a page section and load/scroll trigger');
  }
  const needsMotion = s.approved.page.sections.filter(section => ['load', 'scroll_enter'].includes(section.motion?.trigger));
  if (needsMotion.some(section => !plan.motion.some(m => m.sectionId === section.id))) throw new Error('Provide motion probes for the planned load/scroll entrances');
  return plan;
}
export async function accept(s, core, phase, text) {
  assertRunning(s); validate(s, core);
  if (phase !== s.phase || !stages.includes(phase) || phase === 'capture') throw new Error(`Expected ${s.phase}, not ${phase}`);
  const missing = missingImages(s, core);
  if (missing.length) throw new Error(`Inspect and record ${missing.length} required images before submitting ${phase}`);
  try {
    if (phase === 'brief') {
      const output = core.parseBriefingOutput(text);
      if (output.status === 'not_design') { s.status = 'not-design'; s.phase = 'complete'; return save(s); }
      if (output.status !== 'complete') throw new Error('Complete briefing autonomously; no briefing questions');
      const brief = core.parseDesignBrief({ ...output.brief, originalRequest: s.request });
      s.typography = core.selectTypographyCandidates();
      s.deck = s.references.length ? [] : core.selectReviewedReferences(brief);
      const originals = [...new Set([...s.references, ...core.referenceDirectionAttachments(s.deck)])];
      s.originalReferenceSnapshot = core.snapshotDesignFiles(originals);
      const inputs = path.join(s.run, 'inputs');
      privateDirectory(inputs);
      const local = new Map(originals.map((file, i) => {
        const destination = path.join(inputs, `${i + 1}-${path.basename(file)}`);
        writeFileSync(destination, readFileSync(file), { mode: 0o600, flag: 'wx' });
        return [file, destination];
      }));
      s.references = s.references.map(file => local.get(file));
      s.deck = s.deck.map(ref => ({ ...ref, imagePath: local.get(ref.imagePath), ...(ref.mobileImagePath ? { mobileImagePath: local.get(ref.mobileImagePath) } : {}) }));
      s.referenceSnapshot = core.snapshotDesignFiles([...local.values()]);
      artifact(s, 'brief', brief);
      atomic(path.join(s.run, 'references.json'), { deck: s.deck, snapshots: s.referenceSnapshot, typography: s.typography });
      s.phase = 'brand';
    } else if (phase === 'brand') {
      const brand = core.parseBrandPhaseOutput(text);
      if (s.mode === 'existing' && brand.foundation.strategy === 'create') throw new Error('Existing-app mode must preserve or extend the current identity');
      core.validateTypographySelection(s.approved.brief, brand, s.typography);
      artifact(s, 'brand', brand); s.phase = 'page';
    } else if (phase === 'page') {
      artifact(s, 'page', core.parsePagePhaseOutput(text, s.deck, s.references.map((_, i) => `user-reference-${i + 1}`), true));
      delete s.replanNote;
      s.phase = 'assets';
    } else if (phase === 'assets') {
      const assets = core.parseAssetPhaseOutput(text, s.approved.page, s.workspace, s.references);
      try { core.validateResolvedDesignAssets(assets); } catch (error) {
        if (s.assetReplanned) throw error;
        s.assetReplanned = true;
        s.replanNote = `Asset acquisition failed. Replan Page once, preserving required content and reference geometry. Use native components for an interface that does not yet exist. Keep photography as real assets. Diagnostic: ${error.message}`;
        s.phase = 'page'; s.inspected.page = {}; s.correctionErrors = []; delete s.error;
        return save(s);
      }
      artifact(s, 'assets', assets);
      s.assetSnapshot = core.snapshotDesignAssets(s.workspace, assets);
      s.phase = 'build';
    } else if (phase === 'build' || phase === 'repair') {
      const output = phase === 'build' ? core.parseBuildPhaseOutput(text) : core.parseRepairPhaseOutput(text);
      if (output.status !== 'complete') throw new Error(output.error ?? output.summary);
      s.lastAcceptedSource = validateBuild(s, core, output.files);
      s.history.push({ phase, repairAttempt: s.repairAttempt, output, sourceKey: sourceKey(s) });
      s.phase = phase === 'repair' ? 'capture' : 'preview';
    } else if (phase === 'preview') {
      s.preview = previewPlan(JSON.parse(text), core, s);
      atomic(path.join(s.run, 'preview.json'), s.preview);
      s.artifactHashes.preview = fileHash(path.join(s.run, 'preview.json'));
      s.phase = 'capture';
    } else if (phase === 'review') {
      let review = core.parseReviewPhaseOutput(text);
      // Revalidate source even if the model claims the screenshots look correct.
      scoped(s, () => core.validateDesignSourceQuality(s.workspace, [], s.sourceBaseline, s.approved.assets, s.approved.page));
      const automated = s.capture.findings;
      const ids = new Set(automated.map(f => f.id));
      review = { ...review, findings: [...review.findings.filter(f => !ids.has(f.id)), ...automated] };
      review.verdict = review.findings.length ? 'repair' : 'pass';
      artifact(s, 'review', review); s.review = review;
      if (review.verdict === 'pass') { s.phase = 'complete'; s.status = 'passed'; }
      else if (s.repairAttempt >= 2) { s.phase = 'complete'; s.status = 'findings-remain'; }
      else { s.repairAttempt++; s.phase = 'repair'; s.inspected.repair = {}; }
    }
    s.correctionErrors = []; delete s.error;
    return save(s);
  } catch (error) {
    const previous = s.correctionErrors;
    const planning = ['brand', 'page', 'assets'].includes(phase);
    if (previous.includes(error.message) || previous.length >= (planning ? 3 : 1)) s.status = 'failed';
    else s.correctionErrors.push(error.message);
    s.error = error.message;
    save(s);
    throw error;
  }
}
export async function check(s, core) {
  assertRunning(s); validate(s, core);
  if (!['build', 'repair'].includes(s.phase)) throw new Error('Project checks run during Build or Repair');
  const before = sourceKey(s);
  const results = [];
  for (const [i, c] of s.checks.entries()) {
    const file = path.join(s.run, `check-${s.repairAttempt}-${i}.log`);
    const result = await new Promise(resolve => {
      const child = spawn(c.command, c.args, { cwd: inside(s.workspace, c.cwd ?? '.'), stdio: ['ignore', 'pipe', 'pipe'], shell: false });
      let output = '';
      child.stdout.on('data', b => { output = (output + b.toString()).slice(-200_000); });
      child.stderr.on('data', b => { output = (output + b.toString()).slice(-200_000); });
      child.on('error', error => resolve({ exitCode: null, output: error.message }));
      child.on('close', code => resolve({ exitCode: code, output }));
    });
    writeFileSync(file, result.output, { mode: 0o600 });
    results.push({ name: c.name, exitCode: result.exitCode, log: file });
  }
  s.checkResult = { results, sourceKey: sourceKey(s), passed: before === sourceKey(s) && results.every(r => r.exitCode === 0) };
  s.receipts.push(s.checkResult); save(s);
  return s.checkResult;
}
export async function captureRun(s, modules, recapture = false) {
  assertRunning(s);
  if (recapture) {
    if (s.phase !== 'review') throw new Error('Recapture is for stale Review evidence');
    if (sourceKey(s) !== s.captureSourceKey) {
      if (s.repairAttempt >= 2) throw new Error('Repair budget exhausted; start a new run for further changes');
      s.repairAttempt++;
      s.review = { version: 1, verdict: 'repair', summary: 'Implementation changed after capture.', findings: [{
        id: 'stale_capture', severity: 'blocking', area: 'Browser evidence', evidenceType: 'automated', confidence: 'high',
        evidence: 'Source hashes differ from the last captured implementation.', repair: 'Validate the changes, rerun project checks and capture fresh screenshots.',
      }] };
      s.phase = 'repair'; s.inspected.repair = {};
      validate(s, modules.core);
      return save(s);
    }
    // Do not invalidate the reference/asset checks while permitting changed implementation.
    s.phase = 'capture';
  }
  validate(s, modules.core);
  if (s.phase !== 'capture') throw new Error('Accept a Preview plan or Repair result before capture');
  if (!s.checkResult?.passed || s.checkResult.sourceKey !== sourceKey(s)) throw new Error('Source changed after project checks. Complete a repair with fresh checks before capture.');
  const key = sourceKey(s);
  const directory = path.join(s.run, `capture-${Date.now()}-${s.repairAttempt}`);
  const result = await capture(s, modules, directory);
  if (sourceKey(s) !== key) throw new Error('Source changed during browser capture; recapture a stable revision');
  s.capture = result;
  s.captureFile = path.join(directory, 'browser.json'); s.captureHash = fileHash(s.captureFile);
  s.captureSourceKey = key;
  s.inspected.review = {};
  s.phase = 'review';
  save(s);
  return { ...summary(s), browserEvidence: s.captureFile, findings: result.findings };
}
