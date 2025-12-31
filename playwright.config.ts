/**
 * Playwright configuration for Galata E2E tests.
 * Uses @jupyterlab/galata base configuration.
 */
import { PlaywrightTestConfig } from '@playwright/test';

const baseConfig = require('@jupyterlab/galata/lib/playwright-config');

const config: PlaywrightTestConfig = {
  ...baseConfig,
  testDir: './ui-tests',
  timeout: 60000,  // Reduced from 120s - most tests should be fast
  expect: {
    timeout: 15000,  // Reduced from 30s
  },
  retries: process.env.CI ? 2 : 0,
  // Run tests in parallel - each test creates its own notebook
  // Use 50% of CPUs to avoid overwhelming the Jupyter server
  workers: process.env.CI ? 2 : '50%',
  // Run tests within each file in parallel too
  fullyParallel: true,
  reporter: [
    ['html', { open: 'never' }],
    ['list']
  ],
  use: {
    ...baseConfig.use,
    baseURL: process.env.TARGET_URL ?? 'http://localhost:8888',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
    // Disable windowing mode to prevent minimap button from intercepting cell clicks
    mockSettings: {
      '@jupyterlab/notebook-extension:tracker': {
        windowingMode: 'none'
      }
    }
  },
  webServer: {
    command: 'jupyter lab --config jupyter_server_test_config.py',
    url: 'http://localhost:8888/lab',
    timeout: 120000,
    reuseExistingServer: !process.env.CI,
  },
};

export default config;
