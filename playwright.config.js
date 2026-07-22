// ponytail: minimal config. Boots map_api itself so `npx playwright test` is one command.
const {defineConfig} = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests",
  timeout: 60000,
  fullyParallel: false,   // one shared python server; parallel tabs just fight over it
  workers: 1,
  reporter: [["list"]],
  use: {baseURL: "http://127.0.0.1:8788", trace: "retain-on-failure"},
  webServer: {
    command: "python3 map_api.py",
    url: "http://127.0.0.1:8788/index.html",
    reuseExistingServer: true,
    timeout: 60000,
  },
});
