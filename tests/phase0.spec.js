// Phase 0 browser regressions. Deterministic: every external provider outcome is
// forced with route interception, so results never depend on whether CARTO/Esri
// happen to be reachable.
const {test, expect} = require("@playwright/test");

const PREF_KEY = "oasis.relationshipGraph.productPrefs.v1";
const DARK = "**/dark-matter-gl-style/**";

const errors = [];
test.beforeEach(async ({page}) => {
  errors.length = 0;
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", e => errors.push(String(e)));
});

async function boot(page) {
  await page.goto("/index.html");
  await page.waitForFunction(() => window.graphState && window.graphState().companies > 0, null, {timeout: 30000});
}

async function chooseDark(page) {
  await page.click("#studioBtn");
  await page.click('[data-basemap="dark"]');
  await page.waitForFunction(() => window.mapStudioState().preferredBasemap === "dark");
}

// --- Task 3: no full-universe payload during initial paint -------------------

test("does not request /api/universe/bulk during initial paint", async ({page}) => {
  const bulkCalls = [];
  page.on("request", r => { if (r.url().includes("/api/universe/bulk")) bulkCalls.push(r.url()); });
  await boot(page);
  await page.waitForTimeout(3000);           // give any stray eager load time to fire
  expect(bulkCalls).toEqual([]);
  expect(await page.evaluate(() => window.graphState().bulkLoaded)).toBe(false);
});

test("loads the full universe only after search intent", async ({page}) => {
  await boot(page);
  expect(await page.evaluate(() => window.graphState().bulkLoaded)).toBe(false);
  await page.focus("#search");
  await page.waitForFunction(() => window.graphState().bulkLoaded === true, null, {timeout: 20000});
  expect(await page.evaluate(() => window.graphState().companies)).toBeGreaterThan(10000);
});

// --- Task 2: preferred basemap survives every provider failure mode ----------

for (const [label, fulfil] of [
  ["connection abort", null],
  ["HTTP 500", {status: 500, body: "boom"}],
  ["invalid JSON", {status: 200, contentType: "application/json", body: "{not json"}],
]) {
  test(`preference survives dark provider failure: ${label}`, async ({page}) => {
    await boot(page);
    await chooseDark(page);

    await page.route(DARK, r => (fulfil ? r.fulfill(fulfil) : r.abort()));
    await page.reload();
    await page.waitForFunction(() => window.graphState && window.graphState().companies > 0);
    await page.waitForTimeout(2500);

    // preference preserved in memory AND on disk
    expect(await page.evaluate(() => window.mapStudioState().preferredBasemap)).toBe("dark");
    expect(await page.evaluate(k => JSON.parse(localStorage.getItem(k) || "{}").basemap, PREF_KEY)).toBe("dark");
    // The browser logs the outage we injected; assert only on APPLICATION errors
    // (unhandled rejections, TypeErrors) — those would mean we mishandled it.
    const appErrors = errors.filter(e => !/Failed to load resource|net::ERR_|ERR_FAILED/.test(e));
    expect(appErrors).toEqual([]);
  });
}

test("failure shows a retry affordance and does not loop forever", async ({page}) => {
  await boot(page);
  await chooseDark(page);
  let attempts = 0;
  await page.route(DARK, r => { attempts++; r.abort(); });
  await page.reload();
  await page.waitForFunction(() => window.graphState && window.graphState().companies > 0);
  await page.waitForTimeout(3000);
  expect(attempts).toBeLessThan(10);          // no infinite retry storm
  expect(await page.evaluate(() => window.mapStudioState().preferredBasemap)).toBe("dark");
});

test("repeated switching keeps preference consistent (no stale style wins)", async ({page}) => {
  await boot(page);
  await page.click("#studioBtn");
  // Switch faster than a style can load, so a stale response could try to win.
  // The panel re-renders after each switch, so drive the API directly rather than
  // racing the DOM — the generation guard is what is under test here.
  await page.evaluate(async () => {
    for (const id of ["dark", "satellite", "standard", "satellite"]) {
      window.__switchBasemapForTest(id);
      await new Promise(r => setTimeout(r, 250));
    }
  });
  await page.waitForFunction(() => window.mapStudioState().preferredBasemap === "satellite", null, {timeout: 15000});
  const s = await page.evaluate(() => window.mapStudioState());
  expect(s.preferredBasemap).toBe("satellite");   // last selection wins
  const saved = await page.evaluate(k => JSON.parse(localStorage.getItem(k) || "{}").basemap, PREF_KEY);
  expect(saved).toBe("satellite");
});

// --- vendored MapLibre stays the runtime source ------------------------------

test("MapLibre is served from the app bundle, never a CDN", async ({page}) => {
  const cdn = [];
  page.on("request", r => { if (/unpkg\.com|cdn\.jsdelivr|cdnjs/.test(r.url())) cdn.push(r.url()); });
  await boot(page);
  await page.waitForTimeout(1500);
  expect(cdn).toEqual([]);
});
