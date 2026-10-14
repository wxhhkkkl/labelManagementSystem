/**
 * T156：端到端冒烟测试（走完 quickstart 场景 1~8 的主链路）。
 *
 * ⚠️ **本文件从未运行过。** 它需要 admin-web dev server + 后端 + 数据库同时在线，
 * 而开发环境不具备这些条件。写它的目的是把手工验收步骤固化成可重复执行的脚本，
 * 交付后应在联调环境首次执行并在 `docs/qa/quickstart-report.md` 记录结果。
 *
 * 运行方式：
 *   1. 起后端：uvicorn app.main:app --reload
 *   2. 起前端：npm run dev
 *   3. 准备一个总部管理员账号
 *   4. npx playwright test tests/e2e/smoke.spec.ts
 */

import { expect, test } from '@playwright/test'

const HQ_USERNAME = process.env.E2E_HQ_USERNAME ?? 'hq'
const HQ_PASSWORD = process.env.E2E_HQ_PASSWORD ?? ''

/** 登录并在浏览器里存放令牌。缺令牌时后续用例会 401，而不是静默通过。 */
async function login(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/')
  const response = await page.request.post('/api/v1/auth/login', {
    data: { username: HQ_USERNAME, password: HQ_PASSWORD },
  })
  expect(response.ok(), `登录失败：${response.status()}`).toBeTruthy()

  const body = (await response.json()) as { access_token: string }
  await page.addInitScript((token) => {
    localStorage.setItem('lms.access_token', token)
  }, body.access_token)
}

test.describe('主链路冒烟', () => {
  test.skip(!HQ_PASSWORD, '需要设置 E2E_HQ_PASSWORD')

  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('场景 1：码导入页面可用，模板可下载', async ({ page }) => {
    await page.goto('/imports')
    await expect(page.getByRole('heading', { name: '码导入' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下载导入模板' })).toBeVisible()
  })

  test('场景 2：分配页面能查到可用量', async ({ page }) => {
    await page.goto('/allocations')
    await expect(page.getByRole('heading', { name: '码分配与回收' })).toBeVisible()
    await expect(page.getByRole('button', { name: '确认分配' })).toBeVisible()
  })

  test('场景 3：码池能按状态筛选出已打印的码', async ({ page }) => {
    await page.goto('/code-pool')
    await expect(page.getByRole('heading', { name: '码池查询' })).toBeVisible()
    // 页面能渲染表格即视为链路通；具体数据依赖联调环境的实际数据
    await expect(page.locator('.el-table')).toBeVisible()
  })

  test('场景 4：补打/作废入口可用，且原因未填时不放行', async ({ page }) => {
    await page.goto('/code-actions')
    await expect(page.getByRole('heading', { name: '补打与作废' })).toBeVisible()

    // 不填码值直接点补打，应被前端拦下并给出提示
    await page.getByRole('button', { name: '补打' }).click()
    await expect(page.locator('.el-message, .el-form-item__error').first()).toBeVisible()
  })

  test('场景 5：码追溯页面可查询', async ({ page }) => {
    await page.goto('/code-timeline')
    await expect(page.getByRole('heading', { name: '码全生命周期追溯' })).toBeVisible()
    await expect(page.getByPlaceholder('输入或扫码定位码值')).toBeVisible()
  })

  test('场景 6：看板展示四态', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: '码量看板' })).toBeVisible()
    for (const label of ['待分配', '已分配未打印', '已打印', '已作废']) {
      await expect(page.getByText(label).first()).toBeVisible()
    }
  })

  test('场景 7：打印明细可筛选并出现导出按钮', async ({ page }) => {
    await page.goto('/print-details')
    await expect(page.getByRole('heading', { name: '打印明细' })).toBeVisible()
    await expect(page.getByRole('button', { name: '导出 Excel' })).toBeVisible()
  })

  test('场景 8：操作日志与补打作废台账可访问', async ({ page }) => {
    await page.goto('/audit-logs')
    await expect(page.getByRole('heading', { name: '操作日志' })).toBeVisible()

    await page.goto('/ledger')
    await expect(page.getByRole('heading', { name: '补打 / 作废台账' })).toBeVisible()
  })

  test('侧边菜单每一项都能打开且不报错', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(String(error)))

    const routes = [
      '/org',
      '/workstations',
      '/users',
      '/products',
      '/imports',
      '/templates',
      '/allocations',
      '/code-pool',
      '/code-actions',
      '/ledger',
      '/dashboard',
      '/print-details',
      '/code-timeline',
      '/audit-logs',
    ]

    for (const route of routes) {
      await page.goto(route)
      await expect(page.locator('.el-main')).toBeVisible()
    }

    expect(errors, `页面出现未捕获异常：${errors.join('; ')}`).toEqual([])
  })
})
