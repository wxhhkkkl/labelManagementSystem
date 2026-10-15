import { test, expect } from '@playwright/test'

test('选择产品后只上传一份产品批号表', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('lms.access_token', 'test-token'))
  await page.route('**/api/v1/auth/me', (r) => r.fulfill({ json: { role: 'hq_admin' } }))
  await page.route('**/api/v1/products/options', (r) =>
    r.fulfill({ json: [{ id: 7, code: 'P1', name: '测试产品', status: 'active' }] }),
  )
  let payload = ''
  await page.route('**/api/v1/imports', async (r) => {
    if (r.request().method() === 'POST') {
      payload = r.request().postData() ?? ''
      await r.fulfill({ status: 202, json: { batch_id: 1, batch_no: 'IMP1', status: 'pending' } })
    } else await r.fulfill({ json: [] })
  })
  await page.goto('/imports')
  const button = page.getByRole('button', { name: '上传并导入' })
  await expect(button).toBeDisabled()
  await expect(page.locator('input[type=file]')).toHaveCount(1)
  await page
    .locator('input[type=file]')
    .setInputFiles({
      name: '产品批号表.xlsx',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: Buffer.from('mock workbook'),
    })
  await expect(page.locator('.el-select')).toContainText('测试产品（P1）')
  await expect(button).toBeEnabled()
  await button.click()
  await expect.poll(() => payload).toContain('name="product_id"')
  expect(payload).toContain('name="code_list_file"')
  expect(payload).not.toContain('name="mapping_file"')
  await expect(page.getByText('批次 IMP1', { exact: true })).toBeVisible()
})
