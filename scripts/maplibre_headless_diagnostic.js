#!/usr/bin/env node
// Diagnose headless MapLibre/WebGL console warnings without changing app code.

const fs = require("fs");
const http = require("http");
const path = require("path");
const {spawn} = require("child_process");
const {chromium} = require("@playwright/test");

const ROOT = path.resolve(__dirname, "..");
const EVIDENCE = path.join(ROOT, "docs", "evidence", "performance");
const BASE_URL = process.env.OASIS_PERF_URL || "http://127.0.0.1:8788";

const args = new Map(process.argv.slice(2).map(arg => {
  const [key, ...rest] = arg.replace(/^--/, "").split("=");
  return [key, rest.length ? rest.join("=") : "true"];
}));

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function get(url) {
  return new Promise(resolve => {
    const req = http.get(url, res => {
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

async function startServerIfNeeded() {
  const readyUrl = `${BASE_URL}/index.html`;
  const existing = await get(readyUrl);
  if (existing >= 200 && existing < 500) return null;
  const child = spawn("python3", ["map_api.py"], {
    cwd: ROOT,
    stdio: ["ignore", "pipe", "pipe"],
    env: {...process.env, PYTHONUNBUFFERED: "1"},
  });
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    const status = await get(readyUrl);
    if (status >= 200 && status < 500) return child;
    await wait(500);
  }
  child.kill("SIGTERM");
  throw new Error(`server did not become ready: ${readyUrl}`);
}

function gitValue(...gitArgs) {
  try {
    return require("child_process").execFileSync("git", gitArgs, {cwd: ROOT, encoding: "utf8"}).trim();
  } catch (err) {
    return `unavailable: ${err.message}`;
  }
}

function classifyErrors(errors) {
  return errors.map(text => ({
    text,
    classification: text.includes("shaderPreludeCode")
      ? "headless-maplibre-webgl-shader-warning"
      : /AbortError|signal is aborted|AJAXError/.test(text)
        ? "expected-abort-during-fast-basemap-switch"
        : "unclassified",
  }));
}

async function runVariant(variant, proxyServer) {
  const launchOptions = {headless: true, args: variant.args};
  if (proxyServer) launchOptions.proxy = {server: proxyServer};
  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage();
  const errors = [];
  const requests = [];
  page.on("console", message => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", error => errors.push(String(error)));
  page.on("request", request => requests.push(`${request.method()} ${request.url()}`));
  try {
    await page.goto(`${BASE_URL}/index.html`, {waitUntil: "domcontentloaded"});
    await page.waitForFunction(() => window.graphState && window.graphState().companies > 0, null, {timeout: 30000});
    await page.click("#studioBtn");
    for (const basemap of ["standard", "dark", "satellite", "standard"]) {
      await page.evaluate(id => window.__switchBasemapForTest(id), basemap);
      await page.waitForTimeout(900);
    }
    await page.waitForTimeout(1200);
    const state = await page.evaluate(() => window.mapStudioState?.()).catch(err => ({error: String(err)}));
    return {
      label: variant.label,
      launchArgs: variant.args,
      mapStudioState: state,
      errors: classifyErrors(errors),
      requestCount: requests.length,
      requestedUnpkg: requests.some(url => url.includes("unpkg.com")),
      requestedVendoredMapLibre: requests.some(url => url.includes("/vendor/maplibre-gl/5.6.2/")),
      styleLoaded: state?.styleLoaded === true,
      basemapPreserved: state?.basemap === "standard" && state?.preferredBasemap === "standard",
    };
  } finally {
    await browser.close();
  }
}

async function main() {
  fs.mkdirSync(EVIDENCE, {recursive: true});
  const proxyServer = args.get("proxy-server") || process.env.OASIS_PROXY_SERVER || "";
  const server = await startServerIfNeeded();
  try {
    const variants = [
      {label: "default-headless", args: []},
      {label: "swiftshader", args: ["--use-gl=swiftshader"]},
      {label: "angle-swiftshader", args: ["--use-angle=swiftshader"]},
    ];
    const results = [];
    for (const variant of variants) {
      results.push(await runVariant(variant, proxyServer));
    }
    const payload = {
      capturedAt: new Date().toISOString(),
      commit: gitValue("rev-parse", "HEAD"),
      branch: gitValue("branch", "--show-current"),
      baseUrl: BASE_URL,
      proxyServer: proxyServer || null,
      results,
      conclusion: results.every(result =>
        result.styleLoaded
        && result.basemapPreserved
        && result.errors.every(error => error.classification !== "unclassified")
      )
        ? "headless MapLibre/WebGL warnings classified; app state and basemap behavior preserved"
        : "unclassified MapLibre diagnostic result remains",
    };
    const out = path.join(EVIDENCE, "18-headless-maplibre-diagnostic.json");
    fs.writeFileSync(out, `${JSON.stringify(payload, null, 2)}\n`);
    console.log(`Wrote headless MapLibre diagnostic to ${out}`);
  } finally {
    if (server) server.kill("SIGTERM");
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
