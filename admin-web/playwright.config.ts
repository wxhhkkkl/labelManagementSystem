import { defineConfig, devices } from '@playwright/test'

/**
 * 端到端测试配置（T007）。
 *
 * 需要后台与数据库先启动；冒烟用例见 tests/e2e/smoke.spec.ts（T156）。
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'msedge', use: { ...devices['Desktop Edge'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
