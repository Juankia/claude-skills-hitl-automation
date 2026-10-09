import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.PORTAL_PORT ?? 4317);

export default defineConfig({
  testDir: "./tests",
  // The demo portal keeps filings in memory; tests reset it and must not interleave.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: "npx tsx demo-portal/server.ts",
    url: `http://127.0.0.1:${PORT}/index.html`,
    env: { PORT: String(PORT) },
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
