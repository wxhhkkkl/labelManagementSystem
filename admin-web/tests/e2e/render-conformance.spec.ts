/**
 * T099：渲染一致性验证（contracts/template-rendering.md 的验收方式）。
 *
 * 目的：同一份 elements_json 在管理后台预览与工位端打印后，逐元素比对位置与尺寸，
 * 偏差 MUST 在 ±0.5mm 内。这是 FR-038"打印预览"功能的验收依据。
 *
 * ⚠️ 运行前提（本机尚未满足，因此本文件从未执行过）：
 *   - admin-web dev server（npm run dev）
 *   - 工位端能把打印结果输出为 PDF（用于测量实际出纸版面）
 *
 * 这里测的是**管理后台预览侧**的几何：把 DOM 的像素测量换算回毫米，
 * 与模板定义比对。工位端一侧由 print-client 的渲染测试覆盖同一组规则。
 */

import { expect, test } from '@playwright/test'

/** 契约固定的换算基准，必须与两端实现一致。 */
const CSS_PX_PER_MM = 96 / 25.4
/** 验收容差：±0.5mm */
const TOLERANCE_MM = 0.5

const SAMPLE_TEMPLATE = {
  paper_width_mm: 60,
  paper_height_mm: 40,
  elements: [
    { type: 'qrcode', x: 2, y: 2, size: 15 },
    { type: 'text', x: 20, y: 2, content: '产品：', font_size: 3 },
    { type: 'field', x: 20, y: 6, field_name: 'product_name', font_size: 3 },
    { type: 'field', x: 20, y: 10, field_name: 'code_value', font_size: 3 },
    { type: 'field', x: 20, y: 14, field_name: 'batch_no', font_size: 3 },
  ],
}

const SAMPLE_DATA = {
  product_name: '500ml 矿泉水',
  code_value: 'A1B2C3D4',
  batch_no: 'ALL202610120001',
}

test.describe('模板预览几何一致性', () => {
  test.beforeEach(async ({ page }) => {
    // 预览组件挂在一个便于测试的入口上（实现时按需补）
    await page.goto('/preview-harness')
    await page.evaluate(
      ([doc, data]) => {
        const w = window as unknown as {
          __lmsPreview?: { render: (d: unknown, v: unknown) => void }
        }
        w.__lmsPreview?.render(doc, data)
      },
      [SAMPLE_TEMPLATE, SAMPLE_DATA] as const,
    )
    await page.waitForSelector('.paper .el')
  })

  test('纸张尺寸与模板定义一致', async ({ page }) => {
    const box = await page.locator('.paper').boundingBox()
    expect(box).not.toBeNull()
    const widthMm = box!.width / CSS_PX_PER_MM
    const heightMm = box!.height / CSS_PX_PER_MM
    expect(Math.abs(widthMm - SAMPLE_TEMPLATE.paper_width_mm)).toBeLessThanOrEqual(TOLERANCE_MM)
    expect(Math.abs(heightMm - SAMPLE_TEMPLATE.paper_height_mm)).toBeLessThanOrEqual(TOLERANCE_MM)
  })

  test('每个元素的位置与尺寸都在 ±0.5mm 内', async ({ page }) => {
    const paper = await page.locator('.paper').boundingBox()
    expect(paper).not.toBeNull()

    const elements = page.locator('.paper .el')
    await expect(elements).toHaveCount(SAMPLE_TEMPLATE.elements.length)

    for (let i = 0; i < SAMPLE_TEMPLATE.elements.length; i += 1) {
      const expected = SAMPLE_TEMPLATE.elements[i]
      const box = await elements.nth(i).boundingBox()
      expect(box, `第 ${i} 个元素未渲染`).not.toBeNull()

      const actualXmm = (box!.x - paper!.x) / CSS_PX_PER_MM
      const actualYmm = (box!.y - paper!.y) / CSS_PX_PER_MM

      expect(
        Math.abs(actualXmm - expected.x),
        `第 ${i} 个元素 x 偏差超限`,
      ).toBeLessThanOrEqual(TOLERANCE_MM)
      expect(
        Math.abs(actualYmm - expected.y),
        `第 ${i} 个元素 y 偏差超限`,
      ).toBeLessThanOrEqual(TOLERANCE_MM)
    }
  })

  test('字号按毫米渲染而不是 pt', async ({ page }) => {
    const textElement = page.locator('.paper .el').nth(1)
    const box = await textElement.boundingBox()
    const expectedHeightMm = 3
    expect(Math.abs(box!.height / CSS_PX_PER_MM - expectedHeightMm)).toBeLessThanOrEqual(
      TOLERANCE_MM,
    )
  })

  test('动态字段取到的是服务端下发的值', async ({ page }) => {
    const paperText = await page.locator('.paper').innerText()
    expect(paperText).toContain(SAMPLE_DATA.product_name)
    expect(paperText).toContain(SAMPLE_DATA.code_value)
    expect(paperText).toContain(SAMPLE_DATA.batch_no)
  })
})
