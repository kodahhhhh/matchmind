// Isolated verification fixtures, never imported by the skill's normal workflow.
import { cpSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

export function fixture() {
  const workspace = mkdtempSync(path.join(tmpdir(), 'tastecode-skill-'));
  cpSync('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', path.join(workspace, 'font.ttf'));
  writeFileSync(path.join(workspace, 'index.html'), `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reading room</title><link rel="stylesheet" href="style.css"><script src="script.js" defer></script></head><body><main><h1>Your reading room</h1><p>A quiet place to collect the books you want to read.</p><button id="details-toggle" aria-expanded="false">Show details</button><section id="details" hidden><h2>Keep your next book close</h2><p>Add a title and return when you have a moment to read.</p></section></main></body></html>`);
  writeFileSync(path.join(workspace, 'style.css'), css());
  writeFileSync(path.join(workspace, 'script.js'), `document.querySelector('#details-toggle').addEventListener('click', (event) => {const expanded=event.currentTarget.getAttribute('aria-expanded')==='true';event.currentTarget.setAttribute('aria-expanded',String(!expanded));document.querySelector('#details').hidden=expanded;});`);
  return workspace;
}
export function css(broken = false) {
  return `@font-face{font-family:"Fixture Sans";src:url("font.ttf")}*{box-sizing:border-box}body{margin:0;background:#f4f3ef;color:#222;font-family:"Fixture Sans",sans-serif}main{max-width:900px;margin:auto;padding:80px 24px}h1{font-size:clamp(36px,6vw,64px);line-height:1.12;margin:0 0 24px}p{font-size:18px;line-height:1.6;max-width:580px}button{font:inherit;background:#222;color:white;border:0;border-radius:8px;min-width:140px;min-height:${broken ? '24' : '48'}px;padding:0 16px}section{margin-top:32px}button:focus-visible{outline:3px solid #3472c4;outline-offset:4px}`;
}
export function config(workspace, references = []) {
  return { workspace, mode: 'existing', request: 'Refine this reading room, preserving the layout, Fixture Sans and the working details disclosure. No new animations.', scopes: ['index.html', 'style.css', 'script.js', 'font.ttf'], references,
    checks: [{ name: 'Check disclosure JavaScript', command: 'node', args: ['--check', 'script.js'], cwd: '.' }] };
}
export const brief = { status: 'complete', message: 'Brief complete.', questions: [], brief: {
  originalRequest: 'Refine the existing reading room.', subject: 'Reading room', pageType: 'Product interface', scope: 'Reading room content and disclosure', primaryGoal: 'Browse saved reading', audience: 'Readers', offer: 'Saved books', primaryAction: 'Show details', requiredContent: ['Reading introduction', 'Details disclosure'], constraints: ['Preserve layout and Fixture Sans', 'No new animations'], brandInputs: ['Existing neutral palette and Fixture Sans'], creativeControl: 'Preserve existing identity', explicitAnswers: [], assumptions: [], unresolved: [],
} };
export const brand = { version: 1, foundation: { strategy: 'preserve', existingAssets: ['font.ttf'], assetActions: [{ asset: 'font.ttf', action: 'preserve', reason: 'Existing interface font' }], lockedDecisions: ['Fixture Sans', 'Neutral canvas'], assumptions: [] },
  creativeDirection: { summary: 'Quiet reading interface', traits: [{ quality: 'Readable', boundary: 'not decorative' }], productiveTension: 'Comfortable reading with compact actions', signatureDevice: { description: 'A large left aligned heading above the reading action', status: 'existing', invariants: ['Left alignment', 'Open space'] }, restraint: 'No decorative imagery', avoid: ['Invented ornaments'] },
  colorPalette: [{ name: 'canvas', value: '#f4f3ef', usage: 'Existing canvas' }, { name: 'text', value: '#222222', usage: 'Existing text' }], typefaces: [{ family: 'Fixture Sans', source: 'font.ttf', roles: ['UI'], weights: [400] }], interfaceDirection: 'Open content with one clear action',
  imageDirection: { summary: 'No imagery required', subjects: ['Reading content'], treatment: 'Native text', avoid: ['Decorative images'] }, motionDirection: { summary: 'Preserve static interface', principles: ['Show disclosure state directly'], avoid: ['New entrances'] }, voice: { summary: 'Direct reading guidance', avoid: ['Unsupported claims'] } };
export const page = { version: 1, page: { title: 'Reading room', route: '/', description: 'Your saved reading' },
  architecture: { contract: 'Help readers inspect their reading list', mode: 'operate_monitor', novelty: 'low', grid: 'Single centered reading column', signatureRule: 'Left-aligned heading and action', rhythm: 'Heading, supporting copy, action, details' },
  navigation: [], navigationDesign: { layoutCase: 'reference-navigation', layout: 'No additional navigation in the focused region', behavior: ['Retain page structure'], transformation: { compact: 'Single column', medium: 'Single column', expanded: 'Single column' } },
  sections: [{ id: 'reading', layoutFamily: 'feature', layoutCases: ['user-reference-1'], referenceDirectionId: 'user-reference-1', purpose: 'Inspect reading details', userQuestion: 'Where is my next book?', stage: 'act', dependencies: [], evidence: [], copy: { heading: 'Your reading room', body: ['A quiet place to collect the books you want to read.'], callsToAction: [{ label: 'Show details', target: '#details' }] }, layout: 'Left-aligned heading and copy above a single action', motion: { purpose: 'none', trigger: 'none', behavior: 'Static content', durationMs: 0, easing: 'linear', reducedMotion: 'Static content' }, componentNeeds: [], assetNeeds: [], transformation: { compact: 'Keep one column with 24px edges', medium: 'Center reading column', expanded: 'Cap content at 900px' } }],
  responsive: ['One column at all widths'], interactions: ['Show details reveals the details section'], acceptanceCriteria: ['Readable at 390px and desktop widths'] };
export const assets = { version: 1, assets: [{ id: 'reading_font', kind: 'font', status: 'existing', purpose: 'Preserve reading typography', requirements: ['Local font'], role: 'font', sectionIds: ['reading'], source: { kind: 'project', reference: 'font.ttf' } }] };
export const preview = { version: 1, kind: 'static', cwd: '.', entry: 'index.html', url: 'http://127.0.0.1:4173/', viewports: [{ name: 'desktop', width: 1440, height: 1000 }, { name: 'mobile', width: 390, height: 844 }], interactions: [{ name: 'Focus action', action: 'focus', selector: '#details-toggle' }, { name: 'Reveal details', action: 'click', selector: '#details-toggle', expect: { selector: '#details', visible: true } }], motion: [] };
export const build = { status: 'complete', summary: 'Reading room implementation validated.', files: ['index.html', 'style.css', 'script.js', 'font.ttf'], checks: ['node --check script.js'] };
export const passingReview = { version: 1, verdict: 'pass', summary: 'The captured layout matches the supplied reading reference.', findings: [] };
