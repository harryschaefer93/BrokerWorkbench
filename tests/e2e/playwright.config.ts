import { defineConfig, devices } from '@playwright/test';

/**
 * BrokerWorkbench frontend e2e config.
 *
 * Default: target the live Sweden Central frontend. Override with
 *   $env:BROKER_FRONTEND_URL = "http://localhost:8080"
 * (or any deployed FQDN) to run against a different stack.
 *
 * The legacy `smoke.spec.ts` still references localhost:8080 and
 * self-skips if unreachable, so this default is safe both locally and in CI.
 */
const BASE_URL =
  process.env.BROKER_FRONTEND_URL ??
  'https://ca-frontend-brokerworkbench-dev.kinddune-112ddddc.swedencentral.azurecontainerapps.io';

export default defineConfig({
  testDir: './tests',
  timeout: 180_000,  // chat tests stream tokens from gpt-5; allow generous time
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    // Live SC stack has self-signed cert chain handled by trusted Azure CA;
    // explicit ignoreHTTPSErrors is left default-off so misconfigs surface.
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
