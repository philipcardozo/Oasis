const {defineConfig, devices} = require("@playwright/test");

const baseURL = (process.env.OASIS_PUBLIC_PLAYWRIGHT_BASE_URL || process.env.STAGING_URL || "").replace(/\/$/, "");
if (!baseURL) {
  throw new Error("Set OASIS_PUBLIC_PLAYWRIGHT_BASE_URL or STAGING_URL");
}

const extraHTTPHeaders = {};
if (process.env.OASIS_CF_ACCESS_CLIENT_ID && process.env.OASIS_CF_ACCESS_CLIENT_SECRET) {
  extraHTTPHeaders["CF-Access-Client-Id"] = process.env.OASIS_CF_ACCESS_CLIENT_ID;
  extraHTTPHeaders["CF-Access-Client-Secret"] = process.env.OASIS_CF_ACCESS_CLIENT_SECRET;
}

module.exports = defineConfig({
  testDir: "./tests",
  timeout: 90000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL,
    extraHTTPHeaders,
    ignoreHTTPSErrors: process.env.OASIS_PUBLIC_IGNORE_HTTPS_ERRORS === "true",
    trace: "retain-on-failure",
  },
  projects: [
    {name: "chromium", use: {...devices["Desktop Chrome"]}},
    {name: "firefox", use: {...devices["Desktop Firefox"]}},
    {name: "webkit", use: {...devices["Desktop Safari"]}},
  ],
});
