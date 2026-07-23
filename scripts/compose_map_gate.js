#!/usr/bin/env node
// Real-browser MapLibre gate for the Compose staging target.

const fs = require("fs");
const os = require("os");
const path = require("path");
const {execFileSync} = require("child_process");
const {chromium} = require("@playwright/test");

const ROOT = path.resolve(__dirname, "..");
const EVIDENCE = path.join(ROOT, "docs", "evidence", "performance");
const args = new Map(process.argv.slice(2).map(arg => {
  const [key, ...rest] = arg.replace(/^--/, "").split("=");
  return [key, rest.length ? rest.join("=") : "true"];
}));

const BASE_URL = (args.get("base-url") || process.env.OASIS_COMPOSE_URL || "https://localhost:8443").replace(/\/$/, "");
const PROXY_SERVER = args.get("proxy-server") || process.env.OASIS_PROXYMAN_PROXY || "";
const HEADED = args.get("headed") !== "false";
const CHANNEL = args.get("browser-channel") || "chrome";
const PREF_KEY = "oasis.relationshipGraph.productPrefs.v1";
const VIEW_KEY = "oasis.relationshipGraph.view.v2";

function gitValue(...gitArgs) {
  try {
    return execFileSync("git", gitArgs, {cwd: ROOT, encoding: "utf8"}).trim();
  } catch (err) {
    return `unavailable: ${err.message}`;
  }
}

function macOSVersion() {
  try {
    return execFileSync("sw_vers", ["-productVersion"], {encoding: "utf8"}).trim();
  } catch (_) {
    return null;
  }
}

async function launchBrowser() {
  const launchBase = {
    headless: !HEADED,
    args: ["--ignore-certificate-errors", "--enable-webgl", "--use-gl=swiftshader"],
  };
  try {
    const browser = await chromium.launch({...launchBase, channel: CHANNEL});
    return {browser, requestedHeaded: HEADED, actualHeadless: !HEADED, channel: CHANNEL, fallback: false};
  } catch (err) {
    const browser = await chromium.launch({...launchBase, headless: true});
    return {
      browser,
      requestedHeaded: HEADED,
      actualHeadless: true,
      channel: "bundled-chromium",
      fallback: true,
      fallbackReason: String(err.message || err).slice(0, 300),
    };
  }
}

function listeners(page, bucket) {
  page.on("console", msg => {
    if (msg.type() === "error") bucket.consoleErrors.push(msg.text());
  });
  page.on("pageerror", err => bucket.pageErrors.push(String(err.message || err)));
  page.on("request", req => {
    bucket.requests.push({method: req.method(), url: req.url(), resourceType: req.resourceType()});
  });
  page.on("requestfailed", req => {
    bucket.failedRequests.push({
      method: req.method(),
      url: req.url(),
      resourceType: req.resourceType(),
      failure: req.failure()?.errorText || "unknown",
    });
  });
}

async function newContext(browser, bucket, extra = {}) {
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport: {width: 1440, height: 950},
    recordHar: {path: path.join(EVIDENCE, extra.harName || "24-compose-map-gate.har"), content: "omit"},
    ...(PROXY_SERVER ? {proxy: {server: PROXY_SERVER}} : {}),
    ...extra.contextOptions,
  });
  const page = await context.newPage();
  listeners(page, bucket);
  return {context, page};
}

async function bootGlobe(page) {
  await page.goto(`${BASE_URL}/index.html`, {waitUntil: "domcontentloaded", timeout: 60000});
  await page.waitForFunction(() => window.graphState && window.graphState().companies > 0, null, {timeout: 60000});
  await page.click('#rail [data-rail="map"]');
  await page.waitForFunction(() => window.mapStudioState && window.mapStudioState().styleLoaded === true, null, {timeout: 90000});
}

async function state(page) {
  return page.evaluate(() => ({
    graph: window.graphState?.() || null,
    map: window.mapStudioState?.() || null,
    mapBox: (() => {
      const el = document.querySelector("#map");
      const canvas = document.querySelector("#map canvas");
      const r = el?.getBoundingClientRect();
      const c = canvas?.getBoundingClientRect();
      return {
        display: el ? getComputedStyle(el).display : null,
        width: r ? Math.round(r.width) : 0,
        height: r ? Math.round(r.height) : 0,
        canvasWidth: c ? Math.round(c.width) : 0,
        canvasHeight: c ? Math.round(c.height) : 0,
      };
    })(),
    detailText: document.querySelector("#detail")?.innerText?.slice(0, 500) || "",
    preference: JSON.parse(localStorage.getItem("oasis.relationshipGraph.productPrefs.v1") || "{}").basemap || null,
    savedMode: JSON.parse(localStorage.getItem("oasis.relationshipGraph.view.v2") || "{}").mode || null,
  }));
}

async function switchBasemap(page, id) {
  await page.evaluate(async basemap => window.__switchBasemapForTest(basemap), id);
  await page.waitForFunction(
    basemap => {
      const s = window.mapStudioState?.();
      return s && s.preferredBasemap === basemap && (s.activeBasemap === basemap || s.basemapNotice);
    },
    id,
    {timeout: 45000},
  );
  await page.waitForTimeout(1200);
  return state(page);
}

async function selectEntityViaSearch(page) {
  await page.fill("#search", "Apple");
  await page.waitForSelector("#results [data-pick-id]", {timeout: 30000});
  const first = page.locator("#results [data-pick-id]").first();
  const pickedId = await first.getAttribute("data-pick-id");
  await first.click();
  await page.waitForFunction(
    id => !!id && window.graphState?.().selected === id,
    pickedId,
    {timeout: 30000},
  );
  await page.waitForTimeout(1500);
  return {pickedId, state: await state(page)};
}

async function main() {
  fs.mkdirSync(EVIDENCE, {recursive: true});
  const launch = await launchBrowser();
  const evidence = {
    capturedAt: new Date().toISOString(),
    baseUrl: BASE_URL,
    proxyServer: PROXY_SERVER || null,
    git: {
      branch: gitValue("branch", "--show-current"),
      commit: gitValue("rev-parse", "--short", "HEAD"),
    },
    platform: {
      os: os.platform(),
      arch: os.arch(),
      release: os.release(),
      macOS: macOSVersion(),
    },
    browser: {
      channel: launch.channel,
      requestedHeaded: launch.requestedHeaded,
      actualHeadless: launch.actualHeadless,
      fallback: launch.fallback,
      fallbackReason: launch.fallbackReason || null,
    },
    checks: {},
  };

  const browser = launch.browser;
  try {
    const bucket = {requests: [], failedRequests: [], consoleErrors: [], pageErrors: []};
    const {context, page} = await newContext(browser, bucket, {harName: "24-compose-map-gate-normal.har"});
    await bootGlobe(page);
    evidence.browser.version = await browser.version();
    evidence.checks.initialStandard = await state(page);
    evidence.checks.basemapSwitching = {
      standard: await switchBasemap(page, "standard"),
      dark: await switchBasemap(page, "dark"),
      satellite: await switchBasemap(page, "satellite"),
      standardAgain: await switchBasemap(page, "standard"),
    };
    await page.mouse.move(720, 475);
    await page.mouse.down();
    await page.mouse.move(820, 520);
    await page.mouse.up();
    await page.mouse.wheel(0, -500);
    await page.waitForTimeout(800);
    evidence.checks.zoomPan = await state(page);
    evidence.checks.entitySelection = await selectEntityViaSearch(page);
    await switchBasemap(page, "satellite");
    await page.reload({waitUntil: "domcontentloaded", timeout: 60000});
    await page.waitForFunction(() => window.graphState && window.graphState().companies > 0, null, {timeout: 60000});
    await page.click('#rail [data-rail="map"]');
    await page.waitForFunction(() => window.mapStudioState?.().preferredBasemap === "satellite", null, {timeout: 60000});
    evidence.checks.reloadPreservesBasemap = await state(page);
    const screenshot = path.join(EVIDENCE, "24-compose-map-gate-normal.png");
    await page.screenshot({path: screenshot, fullPage: true});
    evidence.screenshots = {normal: screenshot};
    await context.close();
    evidence.normalCapture = summarize(bucket);

    const failureBucket = {requests: [], failedRequests: [], consoleErrors: [], pageErrors: []};
    const {context: failureContext, page: failurePage} = await newContext(browser, failureBucket, {
      harName: "24-compose-map-gate-provider-failure.har",
    });
    await failureContext.addInitScript(({prefKey, viewKey}) => {
      localStorage.setItem(prefKey, JSON.stringify({basemap: "dark"}));
      localStorage.setItem(viewKey, JSON.stringify({mode: "globe"}));
    }, {prefKey: PREF_KEY, viewKey: VIEW_KEY});
    await failureContext.route("**/dark-matter-gl-style/**", route => route.abort("failed"));
    await failureContext.route("**/basemaps.cartocdn.com/**", route => route.abort("failed"));
    await bootGlobe(failurePage);
    await failurePage.waitForFunction(() => {
      const s = window.mapStudioState?.();
      return s && s.preferredBasemap === "dark" && s.activeBasemap === "standard" && !!s.basemapNotice;
    }, null, {timeout: 60000});
    evidence.checks.providerFailureFallback = await state(failurePage);
    const failureScreenshot = path.join(EVIDENCE, "24-compose-map-gate-provider-failure.png");
    await failurePage.screenshot({path: failureScreenshot, fullPage: true});
    evidence.screenshots.providerFailure = failureScreenshot;
    await failureContext.close();
    evidence.providerFailureCapture = summarize(failureBucket);

    const allRequests = [...evidence.normalCapture.requests, ...evidence.providerFailureCapture.requests];
    const expectedFailures = [
      ...evidence.normalCapture.failedRequests.filter(isExpectedMapCancellation),
      ...evidence.providerFailureCapture.failedRequests.filter(r => /basemaps\.cartocdn\.com|dark-matter-gl-style/.test(r.url)),
      ...evidence.providerFailureCapture.failedRequests.filter(isExpectedMapCancellation),
    ];
    const unexpectedFailures = [
      ...evidence.normalCapture.failedRequests.filter(r => !isExpectedMapCancellation(r)),
      ...evidence.providerFailureCapture.failedRequests.filter(r => !/basemaps\.cartocdn\.com|dark-matter-gl-style/.test(r.url) && !isExpectedMapCancellation(r)),
    ];
    const consoleErrors = [
      ...evidence.normalCapture.consoleErrors,
      ...evidence.providerFailureCapture.consoleErrors,
    ].filter(text => !/Failed to load resource|WebGL|favicon/i.test(text));

    evidence.summary = {
      requestedUnpkg: allRequests.some(r => /unpkg\.com/.test(r.url)),
      requestedVendoredMapLibre: allRequests.some(r => /\/vendor\/maplibre-gl\/5\.6\.2\/maplibre-gl\.js/.test(r.url)),
      expectedProviderFailures: expectedFailures.length,
      unexpectedFailedRequests: unexpectedFailures,
      unexpectedConsoleErrors: consoleErrors,
      externalHosts: [...new Set(allRequests.map(r => {
        try {
          const u = new URL(r.url);
          return /^(localhost|127\.0\.0\.1)$/.test(u.hostname) ? null : u.hostname;
        } catch (_) {
          return null;
        }
      }).filter(Boolean))].sort(),
    };

    evidence.verdict = (
      evidence.checks.initialStandard.map?.styleLoaded === true &&
      evidence.checks.basemapSwitching.standard.map?.preferredBasemap === "standard" &&
      evidence.checks.basemapSwitching.dark.map?.preferredBasemap === "dark" &&
      evidence.checks.basemapSwitching.satellite.map?.preferredBasemap === "satellite" &&
      evidence.checks.zoomPan.mapBox.canvasWidth > 300 &&
      evidence.checks.zoomPan.mapBox.canvasHeight > 200 &&
      evidence.checks.entitySelection.pickedId &&
      evidence.checks.entitySelection.state.graph?.selected === evidence.checks.entitySelection.pickedId &&
      evidence.checks.entitySelection.state.detailText.length > 0 &&
      evidence.checks.reloadPreservesBasemap.map?.preferredBasemap === "satellite" &&
      evidence.checks.providerFailureFallback.map?.preferredBasemap === "dark" &&
      evidence.checks.providerFailureFallback.map?.activeBasemap === "standard" &&
      !evidence.summary.requestedUnpkg &&
      evidence.summary.requestedVendoredMapLibre &&
      evidence.summary.unexpectedFailedRequests.length === 0 &&
      evidence.summary.unexpectedConsoleErrors.length === 0
    ) ? "pass" : "fail";
  } finally {
    await browser.close();
  }

  const out = path.join(EVIDENCE, "24-compose-map-gate.json");
  fs.writeFileSync(out, JSON.stringify(evidence, null, 2) + "\n");
  console.log(JSON.stringify({verdict: evidence.verdict, evidence: out}, null, 2));
  process.exitCode = evidence.verdict === "pass" ? 0 : 1;
}

function summarize(bucket) {
  return {
    requestCount: bucket.requests.length,
    failedRequestCount: bucket.failedRequests.length,
    consoleErrorCount: bucket.consoleErrors.length,
    pageErrorCount: bucket.pageErrors.length,
    requests: bucket.requests,
    failedRequests: bucket.failedRequests,
    consoleErrors: bucket.consoleErrors,
    pageErrors: bucket.pageErrors,
  };
}

function isExpectedMapCancellation(request) {
  if (request.failure !== "net::ERR_ABORTED") return false;
  return /tiles\.openfreemap\.org\/natural_earth|services\.arcgisonline\.com\/ArcGIS\/rest\/services\/World_Imagery|s3\.amazonaws\.com\/elevation-tiles-prod/.test(request.url);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
