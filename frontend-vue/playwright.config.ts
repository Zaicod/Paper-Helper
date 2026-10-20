import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'

const output = process.env.PAPERFLOW_E2E_OUTPUT_DIR || path.resolve('../.tools')

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  outputDir: path.join(output, 'vue-playwright-artifacts'),
  reporter: [['list'], ['json', { outputFile: path.join(output, 'vue-playwright-results.json') }]],
  use: {
    ...devices['Desktop Chrome'],
    ...(process.env.PAPERFLOW_BROWSER_CHANNEL === 'chrome' ? { channel: 'chrome' } : {}),
    baseURL: process.env.PAPERFLOW_E2E_BASE_URL || 'http://127.0.0.1:5173',
    viewport: { width: 1440, height: 1080 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
