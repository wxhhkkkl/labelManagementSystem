import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('lms.access_token', 'test-token'))
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { role: 'hq_admin', display_name: '总部管理员' } }))
})

test('创建前校验必填字段，成功后刷新组织树', async ({ page }) => {
  let created = false
  let posts = 0
  await page.route('**/api/v1/org/tree', route => route.fulfill({ json: created
    ? [{ id: 1, code: 'EAST', name: '华东公司', status: 'active', workstations: [] }] : [] }))
  await page.route('**/api/v1/companies', async route => {
    posts++
    expect(route.request().postDataJSON()).toEqual({ code: 'EAST', name: '华东公司', contact: '李工', region: null })
    created = true
    await route.fulfill({ status: 201, json: { id: 1 } })
  })
  await page.goto('/org')
  await page.getByRole('button', { name: '新增公司' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog.getByText('公司编码不能为空')).toBeVisible()
  await expect(dialog.getByText('公司名称不能为空')).toBeVisible()
  expect(posts).toBe(0)
  await dialog.getByPlaceholder('请输入唯一公司编码').fill(' EAST ')
  await dialog.getByPlaceholder('请输入公司名称').fill('华东公司')
  await dialog.getByPlaceholder('选填').first().fill('李工')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByText('华东公司（EAST）')).toBeVisible()
  expect(posts).toBe(1)
})

test('编码重复时显示错误并保留表单内容', async ({ page }) => {
  await page.route('**/api/v1/org/tree', route => route.fulfill({ json: [] }))
  await page.route('**/api/v1/companies', route => route.fulfill({ status: 422, json: {
    error_code: 'VALIDATION_ERROR', message: '公司编码已存在：EAST', details: {},
  } }))
  await page.goto('/org')
  await page.getByRole('button', { name: '新增公司' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByPlaceholder('请输入唯一公司编码').fill('EAST')
  await dialog.getByPlaceholder('请输入公司名称').fill('华东公司')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('公司编码已存在：EAST')
  await expect(dialog.getByPlaceholder('请输入公司名称')).toHaveValue('华东公司')
})

test('子公司管理员不能访问组织树', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { role: 'sub_admin', display_name: '子公司管理员' } }))
  await page.route('**/api/v1/org/tree', route => route.fulfill({ json: [] }))
  await page.route('**/api/v1/workstations', route => route.fulfill({ json: [] }))
  await page.goto('/org')
  await expect(page).toHaveURL(/\/workstations$/)
  await expect(page.getByRole('button', { name: '新增公司' })).toHaveCount(0)
})
