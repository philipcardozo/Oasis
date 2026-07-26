#!/usr/bin/env node
// Capture browser traffic for OASIS performance work.
//
// Use with Proxyman by passing --proxy-server=http://127.0.0.1:<proxyman-port>
// after enabling SSL proxying/cert trust in Proxyman. Without that flag this
// still records Playwright HAR + a compact JSON summary.

const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");
const {spawn} = require("child_process");
const {chromium} = require("@playwright/test");

const ROOT = path.resolve(__dirname, "..");
const EVIDENCE = path.join(ROOT, "docs", "evidence", "performance");

const args = new Map(process.argv.slice(2).map(arg => {
  const [key, ...rest] = arg.replace(/^--/, "").split("=");
  return [key, rest.length ? rest.join("=") : "true"];
}));
const BASE_URL = (args.get("base-url") || process.env.OASIS_PERF_URL || "http://127.0.0.1:8788").replace(/\/$/, "");
const FLOW_PREFIX = args.get("flow-prefix") || "";
const SUMMARY_FILE = args.get("summary-file") || `${FLOW_PREFIX || "11-browser"}-har-summary.json`;
const NO_START_SERVER = args.get("no-start-server") === "true";
const IGNORE_HTTPS_ERRORS = args.get("ignore-https-errors") === "true"
  || (/^https:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(BASE_URL) && args.get("ignore-https-errors") !== "false");
const SENSITIVE_QUERY_RE = /(?:^|[_-])(?:token|code|secret|password|passwd|key|authorization|credential|session)(?:$|[_-])/i;

function flowName(name) {
  return FLOW_PREFIX ? `${FLOW_PREFIX}-${name}` : name;
}

function ensureEvidenceDir() {
  fs.mkdirSync(EVIDENCE, {recursive: true});
}

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function get(url) {
  return new Promise(resolve => {
    const client = url.startsWith("https:") ? https : http;
    const req = client.get(url, {rejectUnauthorized: false}, res => {
      res.resume();
      res.on("end", () => resolve(res.statusCode || 0));
    });
    req.on("error", () => resolve(0));
    req.setTimeout(750, () => {
      req.destroy();
      resolve(0);
    });
  });
}

async function waitForServer(url, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await get(url);
    if (status >= 200 && status < 500) return;
    await wait(500);
  }
  throw new Error(`server did not become ready: ${url}`);
}

async function startServerIfNeeded() {
  const readyUrl = `${BASE_URL}/index.html`;
  const existing = await get(readyUrl);
  if (existing >= 200 && existing < 500) return null;
  if (NO_START_SERVER) throw new Error(`target did not become ready and --no-start-server was set: ${readyUrl}`);
  const child = spawn("python3", ["map_api.py"], {
    cwd: ROOT,
    stdio: ["ignore", "pipe", "pipe"],
    env: {...process.env, PYTHONUNBUFFERED: "1"},
  });
  child.stdout.on("data", chunk => process.stdout.write(chunk));
  child.stderr.on("data", chunk => process.stderr.write(chunk));
  await waitForServer(readyUrl);
  return child;
}

function gitValue(...gitArgs) {
  try {
    return require("child_process")
      .execFileSync("git", gitArgs, {cwd: ROOT, encoding: "utf8"})
      .trim();
  } catch (err) {
    return `unavailable: ${err.message}`;
  }
}

function sanitizeUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    let sensitive = false;
    for (const [name, value] of [...url.searchParams.entries()]) {
      if (SENSITIVE_QUERY_RE.test(name) && value && value !== "redacted") {
        url.searchParams.set(name, "redacted");
        sensitive = true;
      }
    }
    return {url: url.toString(), sensitive};
  } catch (_) {
    return {url: rawUrl, sensitive: false};
  }
}

function requestKey(request) {
  return `${request.method()} ${sanitizeUrl(request.url()).url}`;
}

async function summarizeFlow(page, requests, consoleErrors, extra = {}) {
  const resources = await page.evaluate(() =>
    performance.getEntriesByType("resource").map(r => ({
      name: r.name,
      initiatorType: r.initiatorType,
      transferSize: r.transferSize,
      encodedBodySize: r.encodedBodySize,
      decodedBodySize: r.decodedBodySize,
      duration: Number(r.duration.toFixed(2)),
    }))
  ).catch(() => []);
  const sanitizedResources = resources.map(resource => {
    const sanitized = sanitizeUrl(resource.name);
    return {...resource, name: sanitized.url, sensitiveUrl: sanitized.sensitive};
  });
  const navigation = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0];
    if (!nav) return null;
    return {
      domContentLoadedMs: Number(nav.domContentLoadedEventEnd.toFixed(2)),
      loadEventMs: Number(nav.loadEventEnd.toFixed(2)),
      transferSize: nav.transferSize,
      encodedBodySize: nav.encodedBodySize,
      decodedBodySize: nav.decodedBodySize,
      duration: Number(nav.duration.toFixed(2)),
    };
  }).catch(() => null);
  const byUrl = new Map();
  for (const req of requests) {
    byUrl.set(req.key, (byUrl.get(req.key) || 0) + 1);
  }
  const duplicates = [...byUrl.entries()]
    .filter(([, count]) => count > 1)
    .map(([key, count]) => ({key, count}))
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
  const slowest = requests
    .filter(r => Number.isFinite(r.durationMs))
    .sort((a, b) => b.durationMs - a.durationMs)
    .slice(0, 20)
    .map(r => ({
      method: r.method,
      url: r.url,
      sensitiveUrl: r.sensitiveUrl || false,
      status: r.status,
      resourceType: r.resourceType,
      durationMs: Number(r.durationMs.toFixed(2)),
      cacheControl: r.cacheControl || null,
      contentEncoding: r.contentEncoding || null,
      contentLength: r.contentLength || null,
      failure: r.failure || null,
    }));
  const externalHosts = [...new Set(requests
    .map(r => {
      try {
        const u = new URL(r.url);
        return /^(127\.0\.0\.1|localhost)$/.test(u.hostname) ? null : u.hostname;
      } catch (_) {
        return null;
      }
    })
    .filter(Boolean))]
    .sort();
  const resourceTransferBytes = resources.reduce((n, r) => n + Number(r.transferSize || 0), 0);
  const sensitiveUrls = [...new Set([
    ...requests.filter(r => r.sensitiveUrl).map(r => r.url),
    ...sanitizedResources.filter(r => r.sensitiveUrl).map(r => r.name),
  ])].sort();
  return {
    requestCount: requests.length,
    failedRequestCount: requests.filter(r => r.failure).length,
    resourceTransferBytes,
    resourceTransferKb: Number((resourceTransferBytes / 1024).toFixed(1)),
    navigation,
    graphState: await page.evaluate(() => window.graphState?.()).catch(() => null),
    mapStudioState: await page.evaluate(() => window.mapStudioState?.()).catch(() => null),
    requestedUniverseBulk: requests.some(r => r.url.includes("/api/universe/bulk")),
    requestedUnpkg: requests.some(r => /unpkg\.com/.test(r.url)),
    sensitiveUrlCount: sensitiveUrls.length,
    sensitiveUrlExamples: sensitiveUrls.slice(0, 10),
    externalHosts,
    duplicates,
    slowest,
    consoleErrors,
    resourceSummary: sanitizedResources
      .sort((a, b) => b.transferSize - a.transferSize)
      .slice(0, 20),
    ...extra,
  };
}

function attachPageListeners(page, requests, consoleErrors) {
  const active = new Map();
  page.on("request", request => {
    const sanitized = sanitizeUrl(request.url());
    const record = {
      key: requestKey(request),
      method: request.method(),
      url: sanitized.url,
      sensitiveUrl: sanitized.sensitive,
      resourceType: request.resourceType(),
      startedAt: Date.now(),
    };
    active.set(request, record);
    requests.push(record);
  });
  page.on("response", async response => {
    const request = response.request();
    const record = active.get(request);
    if (!record) return;
    record.status = response.status();
    record.durationMs = Date.now() - record.startedAt;
    record.cacheControl = response.headers()["cache-control"];
    record.contentEncoding = response.headers()["content-encoding"];
    record.contentLength = response.headers()["content-length"];
  });
  page.on("requestfailed", request => {
    const record = active.get(request);
    if (!record) return;
    record.durationMs = Date.now() - record.startedAt;
    record.failure = request.failure()?.errorText || "request failed";
  });
  page.on("console", message => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", error => consoleErrors.push(String(error)));
}

async function boot(page) {
  await page.goto(`${BASE_URL}/index.html`, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => window.graphState && window.graphState().companies > 0, null, {timeout: 30000});
}

async function waitForDetail(page, text) {
  await page.waitForFunction(
    expected => {
      const detail = document.getElementById("detail");
      return detail?.classList.contains("show") && detail.innerText.includes(expected);
    },
    text,
    {timeout: 30000},
  );
}

async function runFlow(browser, name, flow) {
  const harPath = path.join(EVIDENCE, `${name}.har`);
  const requests = [];
  const consoleErrors = [];
  const context = await browser.newContext({
    baseURL: BASE_URL,
    ignoreHTTPSErrors: IGNORE_HTTPS_ERRORS,
    recordHar: {path: harPath, content: "omit", mode: "full"},
  });
  const page = await context.newPage();
  attachPageListeners(page, requests, consoleErrors);
  let summary;
  try {
    const extra = await flow(page) || {};
    summary = await summarizeFlow(page, requests, consoleErrors, {harPath: path.relative(ROOT, harPath), ...extra});
  } finally {
    await context.close();
  }
  return [name, summary];
}

async function main() {
  ensureEvidenceDir();
  const server = await startServerIfNeeded();
  const proxyServer = args.get("proxy-server") || process.env.OASIS_PROXY_SERVER || "";
  const launchOptions = {headless: args.get("headed") !== "true"};
  if (proxyServer) launchOptions.proxy = {server: proxyServer};
  const browser = await chromium.launch(launchOptions);
  const startedAt = new Date().toISOString();
  const summaries = {
    capturedAt: startedAt,
    commit: gitValue("rev-parse", "HEAD"),
    branch: gitValue("branch", "--show-current"),
    baseUrl: BASE_URL,
    proxyServer: proxyServer || null,
    ignoreHTTPSErrors: IGNORE_HTTPS_ERRORS,
    flows: {},
  };
  try {
    for (const [name, summary] of [
      await runFlow(browser, flowName("03-local-first-paint"), async page => {
        await boot(page);
        await page.waitForTimeout(1500);
        return {flow: "cold first paint"};
      }),
      await runFlow(browser, flowName("04-local-reload"), async page => {
        await boot(page);
        await page.reload({waitUntil: "domcontentloaded"});
        await page.waitForFunction(() => window.graphState && window.graphState().companies > 0);
        await page.waitForTimeout(1000);
        return {flow: "warm reload"};
      }),
      await runFlow(browser, flowName("05-local-search-intent"), async page => {
        await boot(page);
        await page.focus("#search");
        await page.keyboard.type("NVDA");
        await page.waitForFunction(() => window.graphState().bulkLoaded === true, null, {timeout: 25000});
        await page.waitForTimeout(500);
        return {flow: "search intent and bulk load"};
      }),
      await runFlow(browser, flowName("06-local-map-interactions"), async page => {
        await boot(page);
        await page.click("#studioBtn");
        for (const basemap of ["standard", "dark", "satellite", "standard"]) {
          await page.evaluate(id => window.__switchBasemapForTest(id), basemap);
          await page.waitForTimeout(1250);
        }
        return {flow: "Map Studio and basemap switching"};
      }),
      await runFlow(browser, flowName("07-local-dcf-download"), async page => {
        await boot(page);
        const dcf = await page.evaluate(async () => {
          const started = performance.now();
          const response = await fetch("/api/entity/BLK/dcf.xlsx?method=cash_flow");
          const buffer = await response.arrayBuffer();
          return {
            status: response.status,
            bytes: buffer.byteLength,
            durationMs: Number((performance.now() - started).toFixed(2)),
            contentType: response.headers.get("content-type"),
            contentEncoding: response.headers.get("content-encoding"),
            contentLength: response.headers.get("content-length"),
            cacheControl: response.headers.get("cache-control"),
            etag: response.headers.get("etag"),
          };
        });
        return {flow: "DCF workbook fetch", dcf};
      }),
      await runFlow(browser, flowName("12-local-entity-drawer"), async page => {
        await boot(page);
        await page.focus("#search");
        await page.keyboard.type("GM");
        await page.waitForFunction(() => window.graphState().bulkLoaded === true, null, {timeout: 25000});
        await page.evaluate(() => window.pickSearch("GM"));
        await waitForDetail(page, "General Motors");
        await page.waitForTimeout(2500);
        return {
          flow: "entity drawer hydration",
          detailText: await page.locator("#detail").innerText().then(text => text.slice(0, 500)),
        };
      }),
      await runFlow(browser, flowName("13-local-data-quality-panel"), async page => {
        await boot(page);
        await page.click("#dataBtn");
        await page.waitForFunction(
          () => document.getElementById("dataPanel")?.innerText.includes("Data Quality"),
          null,
          {timeout: 30000},
        );
        await page.waitForTimeout(1500);
        return {
          flow: "data quality panel",
          panelText: await page.locator("#dataPanel").innerText().then(text => text.slice(0, 500)),
        };
      }),
      await runFlow(browser, flowName("14-local-report-preview"), async page => {
        await boot(page);
        const report = await page.evaluate(async () => {
          const started = performance.now();
          const response = await fetch("/api/reports/entity/GM");
          const body = await response.json().catch(() => null);
          return {
            status: response.status,
            durationMs: Number((performance.now() - started).toFixed(2)),
            cacheControl: response.headers.get("cache-control"),
            contentEncoding: response.headers.get("content-encoding"),
            contentLength: response.headers.get("content-length"),
            keys: body && typeof body === "object" ? Object.keys(body).sort() : [],
          };
        });
        return {flow: "report preview", report};
      }),
    ]) {
      summaries.flows[name] = summary;
    }
  } finally {
    await browser.close();
    if (server) server.kill("SIGTERM");
  }
  const out = path.join(EVIDENCE, SUMMARY_FILE);
  fs.writeFileSync(out, `${JSON.stringify(summaries, null, 2)}\n`);
  console.log(`Wrote browser performance summary to ${out}`);
}

if (require.main === module) {
  main().catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = {sanitizeUrl};
