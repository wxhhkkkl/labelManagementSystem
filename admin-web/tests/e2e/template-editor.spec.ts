import { expect, test } from '@playwright/test'
const item = {
  id: 1,
  code: 'TPL-A',
  name: '已有标签',
  status: 'active',
  current_version_no: 1,
  version_count: 1,
}
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('lms.access_token', 'test-token'))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: { role: 'hq_admin' } }))
  await page.route('**/api/v1/templates', (route) => route.fulfill({ json: [item] }))
})

test('全部元素属性可编辑，日期与流水号保存，重新打开不串数据', async ({ page }) => {
  const runtimeErrors: string[] = []
  page.on('pageerror', (error) => runtimeErrors.push(error.message))
  let saved: Record<string, unknown> | undefined
  await page.route('**/api/v1/templates', async (route) => {
    if (route.request().method() === 'POST') {
      saved = route.request().postDataJSON()
      await route.fulfill({ status: 201, json: item })
    } else await route.fulfill({ json: [item] })
  })
  await page.route('**/api/v1/templates/1/versions', (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          version_no: 1,
          elements_json: {
            paper_width_mm: 80,
            paper_height_mm: 50,
            elements: [{ type: 'text', x: 4, y: 4, content: '已有内容', font_size: 3, width: 20 }],
          },
        },
      ],
    }),
  )
  await page.setViewportSize({ width: 1500, height: 1000 })
  await page.goto('/templates')
  await page.getByRole('button', { name: '新建模板', exact: true }).click()
  const dialog = page.getByRole('dialog'),
    properties = dialog.locator('.property-panel')
  await dialog.getByRole('button', { name: '二维码', exact: true }).click()
  await expect(dialog.locator('.canvas .el img')).toBeVisible()
  await expect(dialog.locator('.canvas .el img')).toHaveJSProperty('complete', true)
  await properties.locator('.coords input').first().fill('6')
  await properties.locator('.coords input').first().blur()
  await expect(properties.locator('.coords input').first()).toHaveValue('6.00')
  await dialog.getByRole('button', { name: '文本', exact: true }).click()
  await properties.getByPlaceholder('请输入文本内容').fill('产品标签')
  await expect(dialog.locator('.canvas .el').last()).toHaveText('产品标签')
  await properties.locator('.el-checkbox').filter({ hasText: '加粗' }).click()
  await dialog.getByRole('button', { name: '日期', exact: true }).click()
  await expect(dialog.locator('.canvas .el').last()).toHaveText('2026-10-14')
  await dialog.getByRole('button', { name: '流水号', exact: true }).click()
  const prefix = properties.locator('label').filter({ hasText: '前缀' }).locator('input')
  await prefix.fill('SN-')
  await expect(dialog.locator('.canvas .el').last()).toHaveText('SN-000001')
  await dialog.getByRole('button', { name: '复制', exact: true }).click()
  await expect(dialog.locator('.canvas .el')).toHaveCount(5)
  await dialog.getByRole('button', { name: '删除', exact: true }).click()
  await expect(dialog.locator('.canvas .el')).toHaveCount(4)
  await dialog.getByRole('button', { name: '撤销', exact: true }).click()
  await expect(dialog.locator('.canvas .el')).toHaveCount(5)
  await dialog.getByRole('button', { name: '重做', exact: true }).click()
  await expect(dialog.locator('.canvas .el')).toHaveCount(4)
  await dialog.getByPlaceholder('如 TPL-A').fill('TPL-NEW')
  await dialog.getByPlaceholder('如 60×40 标准标签').fill('新标签')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(saved).toMatchObject({
    code: 'TPL-NEW',
    elements: [
      { type: 'qrcode', x: 6 },
      { type: 'text', content: '产品标签', bold: true },
      { type: 'date', date_source: 'print' },
      { type: 'serial', prefix: 'SN-', serial_digits: 6 },
    ],
  })
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await expect(dialog.locator('.canvas .el')).toHaveText('已有内容')
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('button', { name: '新建模板', exact: true }).click()
  await expect(dialog.locator('.canvas .el')).toHaveCount(0)
  expect(runtimeErrors).toEqual([])
})

for (const zoom of [1, 2, 3])
  test(`缩放 ${zoom} 倍时拖动 10mm，元素视觉尺寸和坐标一致`, async ({ page }) => {
    await page.setViewportSize({ width: 1500, height: 1000 })
    await page.goto('/templates')
    await page.getByRole('button', { name: '新建模板', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: '二维码', exact: true }).click()
    await dialog.locator('.editor-tools .el-select').click()
    await page.getByRole('option', { name: `${zoom * 100}%`, exact: true }).click()
    const element = dialog.locator('.canvas .el'),
      box = await element.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.width).toBeCloseTo(((15 * 96) / 25.4) * zoom, 0)
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2)
    await page.mouse.down()
    await page.mouse.move(
      box!.x + box!.width / 2 + ((10 * 96) / 25.4) * zoom,
      box!.y + box!.height / 2,
      { steps: 8 },
    )
    await page.mouse.up()
    await expect(dialog.locator('.coords input').first()).toHaveValue('12.00')
    await dialog.locator('.canvas').press('ArrowRight')
    await expect(dialog.locator('.coords input').first()).toHaveValue('12.10')
    await dialog.getByRole('button', { name: '撤销', exact: true }).click()
    await expect(dialog.locator('.canvas .el')).toHaveCSS('left', /45\.35.*px/)
  })

test('条码固定内容和动态字段可配置，无效编码不能保存', async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 1000 })
  await page.goto('/templates')
  await page.getByRole('button', { name: '新建模板', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const properties = dialog.locator('.property-panel')
  await dialog.getByRole('button', { name: '条码', exact: true }).click()
  await properties.locator('label').filter({ hasText: '内容来源' }).locator('.el-select').click()
  await page.getByRole('option', { name: '固定内容', exact: true }).click()
  await properties.getByPlaceholder('请输入编码内容').fill('')
  await expect(dialog.getByRole('button', { name: '保存', exact: true })).toBeDisabled()
  await properties.getByPlaceholder('请输入编码内容').fill('ABC123')
  await expect(dialog.locator('.canvas img')).toBeVisible()
  await expect(dialog.getByRole('button', { name: '保存', exact: true })).toBeEnabled()
  await dialog.getByRole('button', { name: '动态字段', exact: true }).click()
  await properties.locator('label').filter({ hasText: '绑定字段' }).locator('.el-select').click()
  await page.getByRole('option', { name: '产品名称', exact: true }).click()
  await expect(dialog.locator('.canvas .el').last()).toHaveText('标准产品 A')
  await dialog.getByRole('button', { name: '靠右', exact: true }).click()
  await expect(dialog.locator('.coords input').first()).toHaveValue('30.00')
})
