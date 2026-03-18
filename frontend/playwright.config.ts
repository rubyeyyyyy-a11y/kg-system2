import { defineConfig, devices } from "@playwright/test";

function ensureLocalNoProxy() {
  const local = ["127.0.0.1", "localhost"];
  for (const key of ["NO_PROXY", "no_proxy"] as const) {
    const current = String(process.env[key] || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const merged = [...current];
    for (const token of local) {
      if (!merged.includes(token)) {
        merged.push(token);
      }
    }
    process.env[key] = merged.join(",");
  }
}

ensureLocalNoProxy();

const PORT = Number(process.env.E2E_FRONTEND_PORT || 4173);
const HOST = process.env.E2E_FRONTEND_HOST || "127.0.0.1";
const baseURL = process.env.E2E_BASE_URL || `http://${HOST}:${PORT}`;
const webServerCommand = process.env.E2E_WEB_SERVER_COMMAND || "npm run dev:e2e";
const webServerTimeout = Number(process.env.E2E_WEB_SERVER_TIMEOUT || 180_000);
const reuseExistingServer = process.env.E2E_REUSE_EXISTING_SERVER !== "0";

export default defineConfig({
  testDir: "./e2e/specs",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  timeout: 90_000,
  expect: {
    timeout: 15_000,
  },
  reporter: [["list"], ["html", { open: "never" }]],
  globalSetup: "./e2e/global.setup.ts",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: webServerCommand,
    url: `${baseURL}/`,
    reuseExistingServer,
    timeout: webServerTimeout,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
      },
    },
  ],
});
