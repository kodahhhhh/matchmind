// End-to-end checks of the flows that broke before over plain HTTP (insecure context):
// analyst send, What-if, search. Usage: node scripts/flows.mjs [baseUrl] [outDir]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const base = process.argv[2] ?? "http://100.97.212.47:5180";
const out = process.argv[3] ?? "../docs/frontend/screenshots/flows";
mkdirSync(out, { recursive: true });
const MATCH = "/match/sb%3A3869685";
const browser = await chromium.launch();
let failed = 0;
const check = (ok, msg) => { console.log(`${ok ? "PASS" : "FAIL"} ${msg}`); if (!ok) failed++; };

for (const [vp, size] of [["phone", { width: 480, height: 960 }], ["desktop", { width: 1440, height: 900 }]]) {
  const ctx = await browser.newContext({ viewport: size });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + MATCH, { waitUntil: "networkidle" });
  check(await page.evaluate(() => window.isSecureContext) === base.startsWith("http://localhost"), `${vp}: secure context is ${base.startsWith("http://localhost")}`);

  // analyst
  await page.getByRole("tab", { name: "Ask" }).click();
  const box = page.getByRole("textbox", { name: /ask/i }).first();
  await box.click();
  await box.fill("Who scored the first goal?");
  await box.press("Enter");
  const answered = await page.waitForFunction(() => {
    const el = document.querySelector("[data-testid=answer], .answer");
    return el && el.textContent && el.textContent.length > 40;
  }, null, { timeout: 90000 }).then(() => true).catch(() => false);
  await page.waitForTimeout(1500);
  check(answered, `${vp}: analyst streamed an answer`);
  await page.screenshot({ path: `${out}/analyst-${vp}.png` });

  // what-if
  await page.goto(base + MATCH, { waitUntil: "networkidle" });
  await page.getByRole("tab", { name: "What if" }).click();
  await page.waitForTimeout(600);
  const goal = page.locator("[data-whatif-option]").first();
  if (await goal.count()) await goal.click();
  else await page.getByRole("button", { name: /Di María/ }).first().click();
  const modelled = await page.getByText(/modelled/i).first().waitFor({ timeout: 30000 }).then(() => true).catch(() => false);
  const result = await page.waitForSelector("[data-whatif-result]", { timeout: 30000 }).then(() => true).catch(() => false);
  check(modelled && result, `${vp}: what-if returned a modelled result`);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}/whatif-${vp}.png` });

  // moment card -> ask about this / what if, from the story
  await page.goto(base + MATCH, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Replay on the pitch/ }).first().click();
  const card = await page.getByRole("region", { name: "Selected moment" }).first().waitFor({ timeout: 8000 }).then(() => true).catch(() => false);
  check(card, `${vp}: tapping a story moment opens the moment card`);
  await page.getByRole("region", { name: "Selected moment" }).getByRole("button", { name: /What if/ }).first().click();
  const handed = await page.waitForSelector("[data-whatif-result]", { timeout: 30000 }).then(() => true).catch(() => false);
  check(handed, `${vp}: moment card hands the moment to What if`);
  await page.screenshot({ path: `${out}/moment-whatif-${vp}.png` });

  // search: a team pairing finds the match, a description finds moments
  await page.goto(base + "/", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /search matches, players and moments/i }).first().click();
  await page.keyboard.type("Spain v England");
  const match = await page.getByRole("button", { name: /Spain.*England/ }).first().waitFor({ timeout: 8000 }).then(() => true).catch(() => false);
  check(match, `${vp}: search finds Spain v England`);
  await page.getByRole("textbox").fill("Messi free kick");
  const hits = await page.waitForFunction(() => document.querySelectorAll("[data-search-hit]").length > 2, null, { timeout: 20000 }).then(() => true).catch(() => false);
  check(hits, `${vp}: search returned moments`);
  await page.screenshot({ path: `${out}/search-${vp}.png` });
  check(errors.length === 0, `${vp}: no page errors ${errors.join(" | ")}`);
  await ctx.close();
}
// lite tier (W13 proposal), simulated by rewriting responses: shots only, no possession or momentum, no players
for (const [vp, size] of [["phone", { width: 480, height: 960 }], ["desktop", { width: 1440, height: 900 }]]) {
  const ctx = await browser.newContext({ viewport: size });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const id = "sb%3A3869685";
  await page.route(`**/api/matches/${id}`, async (r) => {
    const res = await r.fetch(); const j = await res.json();
    await r.fulfill({ json: { ...j, data_tier: "lite", capabilities: { shots: true, lineups: true, full_events: false, vaep: false } } });
  });
  await page.route(`**/api/matches/${id}/events`, async (r) => {
    const res = await r.fetch(); const j = await res.json();
    await r.fulfill({ json: { events: j.events.filter((e) => e.type.startsWith("shot")) } });
  });
  await page.route(`**/api/matches/${id}/timeline`, async (r) => {
    const res = await r.fetch(); const j = await res.json();
    for (const m of j.minutes) { m.momentum = null; for (const s of [m.home, m.away]) { s.possession = null; s.field_tilt = null; s.vaep = null; } }
    await r.fulfill({ json: j });
  });
  for (const ep of ["sequences*", "players", "turning-points"]) await page.route(`**/api/matches/${id}/${ep}`, (r) => r.fulfill({ status: 503, body: "unavailable" }));
  await page.route(`**/api/matches/${id}/commentary`, (r) => r.fulfill({ json: { lines: [] } }));
  await page.goto(base + MATCH, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  check(await page.getByText("Shots and stats only.").isVisible(), `${vp} lite: story says shots and stats only`);
  check(await page.getByRole("tab", { name: "What if" }).count() === 0, `${vp} lite: no What if tab`);
  await page.screenshot({ path: `${out}/lite-${vp}.png`, fullPage: false });
  await page.getByRole("tab", { name: "Players" }).click();
  await page.waitForTimeout(800);
  check(await page.getByRole("heading", { name: "Line-ups" }).isVisible(), `${vp} lite: players tab falls back to line-ups`);
  check(errors.length === 0, `${vp} lite: no page errors ${errors.join(" | ")}`);
  await ctx.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
