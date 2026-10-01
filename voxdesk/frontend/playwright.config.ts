import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:8031',
    trace: 'retain-on-failure',
    launchOptions: {
      executablePath: process.env.CHROME_PATH,
      args: [
        '--no-sandbox',
        '--use-fake-ui-for-media-stream',
        '--use-fake-device-for-media-stream',
      ],
    },
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'], defaultBrowserType: 'chromium' } },
  ],
  webServer: {
    command:
      'cd .. && mkdir -p .runtime && ENVIRONMENT=test PROVIDER=fixture PUBLIC_ORIGIN=http://127.0.0.1:8031 DATABASE_URL=sqlite+aiosqlite:///.runtime/e2e.db REQUESTS_PER_MINUTE=500 .venv/bin/uvicorn voxdesk.main:app --host 127.0.0.1 --port 8031 --no-access-log',
    url: 'http://127.0.0.1:8031/health/live',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
