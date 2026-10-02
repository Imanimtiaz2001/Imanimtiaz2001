import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
      args: process.env.PLAYWRIGHT_EXECUTABLE_PATH
        ? ["--no-sandbox", "--disable-dev-shm-usage"]
        : [],
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command:
      "../.venv/bin/uvicorn clearcv.main:app --app-dir ../src --host 127.0.0.1 --port 8000 --no-access-log",
    url: "http://127.0.0.1:8000/health/ready",
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
    env: {
      CLEARCV_DATABASE_URL: "sqlite:///../data/e2e.db",
      CLEARCV_WEB_DIST: "dist",
      CLEARCV_PROVIDER: "local",
      CLEARCV_API_KEY: "",
    },
  },
});
