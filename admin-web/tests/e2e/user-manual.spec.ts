import { expect, test } from '@playwright/test'
import { manualSections } from '../../src/content/userManual'

test('总部可进入说明、按打印端分类并放大对应截图', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('lms.access_token', 'manual-test'))
  await page.route('**/api/v1/auth/me', route => route.fulfill({json:{role:'hq_admin',display_name:'演示管理员'}}))
  await page.route('**/api/v1/org/tree', route => route.fulfill({json:[]}))
  await page.goto('/org')
  await page.locator('.help-shortcut').click()
  await expect(page).toHaveURL(/\/help$/)
  await expect(page.locator('.manual-section')).toHaveCount(23)
  await expect(page.getByRole('textbox',{name:'搜索使用说明'})).toHaveCount(0)
  await page.locator('.el-radio-button').filter({hasText:/^打印端$/}).click()
  await expect(page.locator('.manual-section')).toHaveCount(6)
  await page.locator('.manual-image').first().click()
  await expect(page.locator('.manual-zoom')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.manual-zoom')).toHaveCount(0)
  await page.locator('.el-radio-button').filter({hasText:/^打印端$/}).click()
  await expect(page.locator('.manual-section')).toHaveCount(6)
  // 每个截图引用都必须真实存在，避免上线后出现破图。
  const pictures=new Set(manualSections.flatMap(section=>(section.images ?? []).map(picture=>picture.file)))
  await Promise.all([...pictures].map(async file=>{
    const response=await page.request.get(`/manual/${file}`)
    expect(response.ok(),file).toBe(true)
    expect(response.headers()['content-type'],file).toContain('image/png')
  }))
})

test('分公司管理员也能查看帮助，其他目录权限不扩展',async({page})=>{
  await page.addInitScript(()=>localStorage.setItem('lms.access_token','manual-test'))
  await page.route('**/api/v1/auth/me',route=>route.fulfill({json:{role:'sub_admin',display_name:'演示分公司管理员',company:{id:1,name:'演示公司'}}}))
  await page.goto('/help')
  await expect(page.getByRole('heading',{name:'标签管理系统 · 使用说明'})).toBeVisible()
  await expect(page.locator('nav a[href="/help"]')).toHaveCount(1)
  await expect(page.locator('nav a[href="/products"]')).toHaveCount(0)
  await expect(page.locator('nav a[href="/imports"]')).toHaveCount(0)
  await expect(page.getByRole('textbox',{name:'搜索使用说明'})).toHaveCount(0)
  await expect(page.locator('.manual-notice')).toHaveCount(0)
})
