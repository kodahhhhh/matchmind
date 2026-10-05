// Screenshot every screen at desktop and phone width. Usage:
//   node scripts/shots.mjs <outDir> [baseUrl] [only-substring]
// Logs console errors and failed requests per screen so regressions show up next to the pictures.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const out = process.argv[2] ?? "../docs/frontend/screenshots/latest";
const base = process.argv[3] ?? "http://localhost:5180";
const only = process.argv[4];
mkdirSync(out, { recursive: true });

const MATCH = "/match/sb%3A3869685";
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, phone: { width: 480, height: 960 } };

/** name, path, optional action run before the shot, full page? */
const SCREENS = [
  ["home", "/", null, true],
  ["home-top", "/", null, false],
  ["match", MATCH, null, false],
  ["match-full", MATCH, null, true],
  ["match-moment", MATCH, async (p) => { await p.getByRole("button", { name: /Replay on the pitch/ }).first().click(); await p.waitForTimeout(2500); }, false],
  ["match-ask", MATCH, async (p) => { await p.getByRole("tab", { name: "Ask" }).click(); await p.waitForTimeout(1200); }, false],
  ["match-players", MATCH, async (p) => { await p.getByRole("tab", { name: "Players" }).click(); await p.waitForTimeout(1200); }, false],
  ["match-whatif", MATCH, async (p) => { await p.getByRole("tab", { name: "What if" }).click(); await p.waitForTimeout(1200); }, false],
  ["search", "/", async (p) => { await p.keyboard.press("Control+k"); await p.keyboard.type("header from a corner"); await p.waitForTimeout(2500); }, false],
  ["players", "/players", null, true],
  ["backtest", "/backtest", null, true],
  ["notfound", "/nope", null, false],
];

async function clickText(p, text) {
  const el = p.getByRole("button", { name: text, exact: true }).first();
  if (await el.count()) await el.click();
  else await p.getByText(text, { exact: true }).first().click();
  await p.waitForTimeout(900);
}

const browser = await chromium.launch();
for (const [vp, size] of Object.entries(VIEWPORTS)) {
  const ctx = await browser.newContext({ viewport: size, deviceScaleFactor: 1, reducedMotion: "no-preference" });
  for (const [name, path, act, full] of SCREENS) {
    if (only && !name.includes(only)) continue;
    const page = await ctx.newPage();
    const problems = [];
    page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text().slice(0, 200)}`));
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message.slice(0, 200)}`));
    page.on("requestfailed", (r) => problems.push(`failed: ${r.url()}`));
    const t0 = Date.now();
    await page.goto(base + path, { waitUntil: "networkidle" }).catch((e) => problems.push(`goto: ${e.message}`));
    const loadMs = Date.now() - t0;
    await page.waitForTimeout(1800);
    if (act) await act(page).catch((e) => problems.push(`action: ${e.message.slice(0, 160)}`));
    if (full) {
      // pages scroll inside a container, so grow the viewport to the content height: everything is in view at once
      const h = await page.evaluate(() => Math.max(document.documentElement.scrollHeight,
        ...[...document.querySelectorAll("*")].filter((n) => /(auto|scroll)/.test(getComputedStyle(n).overflowY)).map((n) => n.scrollHeight)));
      await page.setViewportSize({ width: size.width, height: Math.min(h, 12000) });
      await page.waitForTimeout(2200);
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    const file = `${out}/${name}-${vp}.png`;
    await page.screenshot({ path: file, fullPage: full });
    console.log(`${vp.padEnd(7)} ${name.padEnd(14)} ${String(loadMs).padStart(5)}ms${overflow ? "  H-OVERFLOW" : ""}${problems.length ? "\n    " + problems.join("\n    ") : ""}`);
    await page.close();
    if (full) await ctx.pages()[0]?.setViewportSize(size);
  }
  await ctx.close();
}
await browser.close();
