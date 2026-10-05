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
  await page.getByRole("button", { name: /what if/i }).first().click();
  await page.waitForTimeout(600);
  const goal = page.locator("[data-whatif-option]").first();
  if (await goal.count()) await goal.click();
  else await page.getByRole("button", { name: /Di María/ }).first().click();
  const modelled = await page.getByText(/modelled/i).first().waitFor({ timeout: 30000 }).then(() => true).catch(() => false);
  const result = await page.waitForSelector("[data-whatif-result]", { timeout: 30000 }).then(() => true).catch(() => false);
  check(modelled && result, `${vp}: what-if returned a modelled result`);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}/whatif-${vp}.png` });

  // search
  await page.goto(base + "/", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /search/i }).first().click();
  await page.keyboard.type("Messi free kick");
  const hits = await page.waitForSelector("[data-search-hit]", { timeout: 20000 }).then(() => true).catch(() => false);
  check(hits, `${vp}: search returned hits`);
  await page.screenshot({ path: `${out}/search-${vp}.png` });
  check(errors.length === 0, `${vp}: no page errors ${errors.join(" | ")}`);
  await ctx.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
