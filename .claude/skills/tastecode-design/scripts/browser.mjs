import path from 'node:path';
import { atomic, fileHash, inside, privateDirectory } from './files.mjs';

export function localURL(value) {
  const url = new URL(value);
  if (url.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || !url.port || url.username || url.password)
    throw new Error('Preview must use an explicit HTTP loopback origin and port');
  return url.href;
}
function finding(id, evidence, repair, area = 'Browser') {
  return { id, severity: 'blocking', area, evidenceType: 'automated', confidence: 'high', evidence, repair };
}
export async function capture(state, modules, directory) {
  const { playwright, preview, core, audit, settle } = modules;
  const plan = state.preview;
  if (!plan) throw new Error('No preview plan');
  let owned;
  let browser;
  privateDirectory(directory);
  try {
    const url = plan.kind === 'existing' ? localURL(plan.url) : (owned = await preview.startDesignPreview(state.workspace, plan)).url;
    browser = await playwright.chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const screenshots = [];
    const findings = [];
    const evidence = [];
    const variants = ['no-preference', 'reduce'];
    for (const viewport of plan.viewports) for (const reducedMotion of variants) {
      const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height }, reducedMotion,
        ...(plan.storageState ? { storageState: inside(state.workspace, plan.storageState) } : {}) });
      const page = await context.newPage();
      const runtimeErrors = [];
      page.on('pageerror', error => runtimeErrors.push(error.message));
      // Permit asset/CDN requests, but keep document navigation within the chosen app.
      await context.route('**/*', route => {
        const req = route.request();
        if (req.isNavigationRequest() && new URL(req.url()).origin !== new URL(url).origin) return route.abort();
        return route.continue();
      });
      const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
      if (!response?.ok()) throw new Error(`Preview responded ${response?.status() ?? 'without a document'}`);
      if (plan.region) await page.locator(plan.region).waitFor({ state: 'visible' });
      await page.evaluate(settle.PREVIEW_SETTLE_SCRIPT);
      // Recheck after scrolling has activated lazy media. The original settle script tolerates errors.
      const readiness = await page.evaluate(async ({ families, region }) => {
        await Promise.race([document.fonts.ready, new Promise(resolve => setTimeout(resolve, 5000))]);
        const root = region ? document.querySelector(region) : document;
        if (!root) throw new Error('Configured audit region is missing');
        const failedImages = [...root.querySelectorAll('img')].filter(img => !img.complete || img.naturalWidth === 0).map(img => ({ alt: img.alt, source: img.getAttribute('src')?.slice(0, 200) }));
        const missingFonts = families.flatMap(({ family, weights }) => weights.map(weight => ({ family, weight,
          loaded: [...document.fonts].some(face => {
            const normalizedWeight = face.weight === 'normal' ? '400' : face.weight === 'bold' ? '700' : face.weight;
            return face.family.replace(/["']/g, '') === family && face.status === 'loaded' && (normalizedWeight === String(weight) || (normalizedWeight.includes(' ') && Number(normalizedWeight.split(' ')[0]) <= weight && Number(normalizedWeight.split(' ').at(-1)) >= weight));
          }),
          usable: document.fonts.check(`${weight} 16px "${family}"`),
        }))).filter(font => !font.loaded || !font.usable);
        return { failedImages, missingFonts, horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1, height: document.documentElement.scrollHeight };
      }, { families: state.approved.brand.typefaces, region: plan.region });
      const label = `${viewport.name}-${reducedMotion}`;
      if (readiness.failedImages.length) findings.push(finding(`images_${label}`, JSON.stringify(readiness.failedImages), 'Load every planned image successfully.'));
      if (readiness.missingFonts.length) findings.push(finding(`fonts_${label}`, JSON.stringify(readiness.missingFonts), 'Load the approved FontFace and required weights; a fallback declaration is insufficient.'));
      if (readiness.horizontalOverflow) findings.push(finding(`overflow_${label}`, 'Document is wider than the viewport', 'Fix horizontal overflow.'));
      let script = audit.PREVIEW_DOM_AUDIT_SCRIPT;
      if (plan.region) script = script.replace('document.querySelectorAll(interactiveSelector)', `document.querySelector(${JSON.stringify(plan.region)}).querySelectorAll(interactiveSelector)`);
      const domAudit = await page.evaluate(script);
      // Whole-document heading count stays visible; only target selection is scoped for existing UI.
      const domReview = core.enforceDomAuditFindings({ version: 1, verdict: 'pass', summary: 'DOM audit', findings: [] }, [{ path: '', ...viewport, domAudit }]);
      for (const f of domReview.findings) findings.push({ ...f, id: `${f.id}_${label}` });
      const actionResults = [];
      for (const action of plan.interactions ?? []) {
        try {
          const locator = action.selector ? page.locator(action.selector) : null;
          if (action.action === 'click') await locator.click();
          else if (action.action === 'fill') await locator.fill(action.value);
          else if (action.action === 'press') await locator.press(action.key);
          else if (action.action === 'hover') await locator.hover();
          else if (action.action === 'focus') {
            await locator.focus();
            if (!await locator.evaluate(el => document.activeElement === el)) throw new Error('Focus did not reach the control');
          } else if (action.action === 'scroll') await locator.scrollIntoViewIfNeeded();
          if (action.expect) {
            const target = page.locator(action.expect.selector);
            if (action.expect.visible !== undefined && await target.isVisible() !== action.expect.visible) throw new Error('Visibility assertion failed');
            if (action.expect.text !== undefined && !(await target.innerText()).includes(action.expect.text)) throw new Error('Text assertion failed');
            if (action.expect.attribute && await target.getAttribute(action.expect.attribute.name) !== action.expect.attribute.value) throw new Error('Attribute assertion failed');
          }
          actionResults.push({ ...action, passed: true });
        } catch (error) {
          actionResults.push({ ...action, passed: false, error: error.message });
          findings.push(finding(`interaction_${label}_${actionResults.length}`, `${action.name}: ${error.message}`, 'Repair the interaction and rerun its assertion.'));
        }
      }
      const motionResults = [];
      if ((plan.motion ?? []).length) {
        // Observe animations on a fresh load, before entrance animations finish.
        await page.addInitScript(() => {
          window.__tasteAnimations = [];
          const seen = new WeakSet();
          const timer = setInterval(() => {
            for (const a of document.getAnimations()) if (!seen.has(a)) {
              seen.add(a);
              const el = a.effect?.target;
              if (el) window.__tasteAnimations.push({ id: el.id, tag: el.tagName, classes: el.className,
                target: el, duration: a.effect.getTiming().duration, frames: a.effect.getKeyframes().map(f => ({ opacity: f.opacity, transform: f.transform })) });
            }
          }, 16);
          setTimeout(() => clearInterval(timer), 15000);
        });
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(120);
        for (const motion of plan.motion) {
          if (motion.trigger === 'scroll') await page.locator(motion.selector).scrollIntoViewIfNeeded();
          await page.waitForTimeout(120);
          const observed = await page.evaluate(selector => {
            const el = document.querySelector(selector);
            if (!el) return { found: false, count: 0 };
            const animations = (window.__tasteAnimations ?? []).filter(a => a.target === el || el.contains(a.target));
            return { found: true, count: animations.filter(a => a.duration > 0).length };
          }, motion.selector);
          const passed = observed.found && (reducedMotion === 'reduce' ? observed.count === 0 : observed.count > 0);
          motionResults.push({ ...motion, reducedMotion, observed, passed });
          if (!passed) findings.push(finding(`motion_${label}_${motionResults.length}`, JSON.stringify(motionResults.at(-1)), 'Wire the planned animation trigger and disable motion under reduced motion.'));
        }
        for (let i = 0; i < 2; i++) {
          await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight));
          await page.waitForTimeout(80);
          await page.evaluate(() => scrollTo(0, 0));
          await page.waitForTimeout(80);
        }
        await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight / 2));
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.setViewportSize({ width: viewport.width + 1, height: viewport.height });
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await page.waitForTimeout(300);
        for (const motion of plan.motion) {
          const visible = await page.locator(motion.selector).evaluate(el => {
            for (let current = el; current; current = current.parentElement) {
              const s = getComputedStyle(current);
              if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) < 0.05) return false;
            }
            return el.getBoundingClientRect().height > 0;
          });
          if (!visible) findings.push(finding(`motion_visibility_${label}_${motionResults.length}`, motion.selector, 'Keep content visible after scrolling, resize, reload and reduced-motion changes.'));
        }
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.emulateMedia({ reducedMotion });
      }
      // Capture the default page separately from interaction/motion test state.
      await page.goto(url, { waitUntil: 'domcontentloaded' });
      await page.evaluate(settle.PREVIEW_SETTLE_SCRIPT);
      if (runtimeErrors.length) findings.push(finding(`runtime_${label}`, JSON.stringify([...new Set(runtimeErrors)]), 'Fix browser runtime errors.'));
      const file = path.join(directory, `${label}.png`);
      await page.screenshot({ path: file, fullPage: true, timeout: 30_000 });
      screenshots.push({ path: file, width: viewport.width, height: viewport.height, domAudit,
        reducedMotion, sha256: fileHash(file) });
      evidence.push({ viewport, reducedMotion, readiness, actionResults, motionResults, runtimeErrors });
      await context.close();
    }
    const result = { version: 1, url, previewOwned: Boolean(owned), screenshots, findings, evidence };
    atomic(path.join(directory, 'browser.json'), result);
    return result;
  } finally {
    if (browser) await browser.close();
    if (owned) await owned.stop();
  }
}
