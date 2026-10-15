import { expect, test } from '@playwright/test'

test('未登录时展示登录页，登录后返回原页面，退出后清除令牌', async ({ page }) => {
  await page.route('**/api/v1/auth/login', async (route) => {
    expect(route.request().postDataJSON()).toEqual({ username: 'admin', password: 'test-password' })
    await route.fulfill({ json: { access_token: 'test-token' } })
  })
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { role: 'hq_admin' } }))
  await page.route('**/api/v1/org/tree', (route) => route.fulfill({ json: [] }))
  await page.goto('/org')
  await expect(page).toHaveURL(/\/login\?redirect=/)
  await expect(page.getByRole('button', { name: '退出登录' })).toHaveCount(0)
  await page.getByPlaceholder('请输入账号').fill('admin')
  await page.getByPlaceholder('请输入密码').fill('test-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/org$/)
  await expect(page.getByRole('heading', { name: '组织树' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '组织树' })).toBeVisible()
  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => localStorage.getItem('lms.access_token'))).toBeNull()
})

test('密码错误时保留登录页并展示服务端错误', async ({ page }) => {
  await page.route('**/api/v1/auth/login', (route) => route.fulfill({
    status: 401, json: { error_code: 'INVALID_CREDENTIALS', message: '账号或密码错误', details: {} },
  }))
  await page.goto('/login')
  await page.getByPlaceholder('请输入账号').fill('admin')
  await page.getByPlaceholder('请输入密码').fill('incorrect')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('账号或密码错误')
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => localStorage.getItem('lms.access_token'))).toBeNull()
})

test('失效令牌返回登录页并清除登录状态', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('lms.access_token', 'expired-token'))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({
    status: 401, json: { error_code: 'INVALID_CREDENTIALS', message: '令牌已失效', details: {} },
  }))
  await page.goto('/org')
  await expect(page).toHaveURL(/\/login\?redirect=/)
  expect(await page.evaluate(() => localStorage.getItem('lms.access_token'))).toBeNull()
})
