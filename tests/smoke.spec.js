// Browser smoke tests for the core OASIS journey.
// Run: npx playwright test   (needs `python3 map_api.py` on :8788 — see playwright.config.js)
// ponytail: one file, no fixtures/page-objects. Add more only when a real regression escapes.
const {test, expect} = require("@playwright/test");

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

test("app boots from the core payload without the full universe", async ({page}) => {
  // Phase 0: the ~6 MB bulk payload must NOT be on the initial-paint path.
  await boot(page);
  const s = await page.evaluate(() => window.graphState());
  expect(s.companies).toBeGreaterThan(500);      // core payload hydrated
  expect(s.companies).toBeLessThan(5000);        // but not the full 14.6k universe
  expect(s.bulkLoaded).toBe(false);
  expect(s.svgNodes).toBeGreaterThan(0);
  expect(errors).toEqual([]);
});

test("cold load stays within the payload budget", async ({page}) => {
  // Guards the gzip/ETag work: bytes ON THE WIRE, not decoded size.
  await boot(page);
  const kb = await page.evaluate(() =>
    performance.getEntriesByType("resource").reduce((n, r) => n + r.transferSize, 0) / 1024);
  expect(kb).toBeLessThan(3000);
});

test("reload is served from cache", async ({page}) => {
  await boot(page);
  await page.reload();
  await page.waitForFunction(() => window.graphState && window.graphState().companies > 0);
  // "Served from cache" means no resource re-downloads its full body. A cache hit
  // has transferSize 0; a 304 revalidation (which happens once max-age=60 lapses
  // during a slow suite) transfers only headers. A full re-download transfers a
  // body comparable to its encoded size — that is what must not happen.
  const redownloaded = await page.evaluate(() =>
    performance.getEntriesByType("resource")
      .filter(r => r.encodedBodySize > 0 && r.transferSize >= r.encodedBodySize)
      .map(r => r.name.split("/").pop()));
  expect(redownloaded).toEqual([]);
});

test("search focuses an entity and opens the drawer", async ({page}) => {
  await boot(page);
  await page.keyboard.press("Meta+k");
  await page.keyboard.type("NVDA");
  await page.waitForTimeout(400);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.graphState().selected, null, {timeout: 10000});
  expect(await page.evaluate(() => window.graphState().selected)).toBeTruthy();
  expect(errors).toEqual([]);
});

test("Map Studio switches basemap and preserves overlays", async ({page}) => {
  await boot(page);
  const before = await page.evaluate(() => window.mapStudioState());
  await page.click("#studioBtn");
  await expect(page.locator("#studioPanel")).toBeVisible();
  // Drive the switch through the exposed hook: the panel re-renders on every
  // basemap change, so clicking a card can race the re-render.
  await page.evaluate(() => window.__switchBasemapForTest("satellite"));
  await page.waitForFunction(() => window.mapStudioState().basemap === "satellite", null, {timeout: 15000});
  const after = await page.evaluate(() => window.mapStudioState());
  expect(after.basemap).toBe("satellite");
  // terrain + overlays must survive the style swap (the whole point of the style.load re-add path)
  expect(after.terrain).toBe(before.terrain);
  expect(after.terrainExaggeration).toBe(before.terrainExaggeration);
  expect(after.activeOverlays).toBe(before.activeOverlays);
});

// KNOWN BUG (Prompts/18 §2): initMapGlobe's catch overwrites productPrefs.basemap
// with "standard" and persists it, so one failed CDN style load destroys the user's
// saved choice. Reproduces 4/4 in isolation. test.fail() keeps the suite honest and
// flips to a failure the moment someone fixes it — delete this line with the fix.
test("saved basemap choice survives a CDN style failure", async ({page}) => {
  // Invariant: a failed style load may DEGRADE the render to standard, but must never
  // destroy the user's stored choice. We force the failure instead of relying on
  // network luck, so this is deterministic rather than cache-order dependent.
  const KEY = "oasis.relationshipGraph.productPrefs.v1";
  await boot(page);
  await page.click("#studioBtn");
  await page.click('[data-basemap="dark"]');
  await page.waitForFunction(() => window.mapStudioState().basemap === "dark");

  await page.route("**/dark-matter-gl-style/**", r => r.abort());  // simulate CDN outage
  await page.reload();
  await page.waitForFunction(() => window.graphState && window.graphState().companies > 0);

  const saved = await page.evaluate(k => JSON.parse(localStorage.getItem(k) || "{}").basemap, KEY);
  expect(saved).toBe("dark");   // today: "standard" — the outage silently ate the choice
});

test("no secrets or API keys reach the frontend", async ({page}) => {
  const suspicious = [];
  page.on("request", r => {
    const u = r.url();
    if (/[?&](api[_-]?key|access[_-]?token|apikey|secret|signature)=/i.test(u)) suspicious.push(u);
  });
  await boot(page);
  const html = await page.content();
  expect(suspicious).toEqual([]);
  expect(html).not.toMatch(/sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}/);
});
