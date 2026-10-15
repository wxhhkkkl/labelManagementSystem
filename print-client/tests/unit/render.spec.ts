/**
 * T085（工位端侧）：模板渲染换算。
 *
 * 与管理后台的 render.spec.ts 跑的是**同一组契约用例**（contracts/template-rendering.md），
 * 但导入的是本端独立实现。两端都过，才说明"所见即所打"成立。
 */

import { describe, expect, it } from 'vitest'

import {
  CSS_PX_PER_MM,
  PRINT_SCALE_FACTOR,
  RenderError,
  clipToPaper,
  elementSizeMm,
  elementStyle,
  fontFamilyChain,
  mmToPx,
  renderTemplate,
  renderToString,
  resolveFieldValue,
  type TemplateDoc,
} from '../../src/print-render/renderer'

const doc: TemplateDoc = {
  paper_width_mm: 60,
  paper_height_mm: 40,
  elements: [],
}

describe('换算基准', () => {
  it('uses the fixed 96dpi ratio', () => {
    expect(CSS_PX_PER_MM).toBeCloseTo(3.7795275591, 9)
  })

  it('converts 10mm to 37.795275591px', () => {
    expect(mmToPx(10)).toBeCloseTo(37.795275591, 6)
  })

  it('converts 0mm to 0px', () => {
    expect(mmToPx(0)).toBe(0)
  })
})

describe('缩放入口', () => {
  it('keeps the print scale factor at 100%', () => {
    // 打印侧恒定 100%，否则同一模板在不同机器上印出不同尺寸
    expect(PRINT_SCALE_FACTOR).toBe(100)
  })
})

describe('元素尺寸', () => {
  it('derives qrcode size', () => {
    expect(elementSizeMm({ type: 'qrcode', x: 0, y: 0, size: 12 })).toEqual({
      width: 12,
      height: 12,
    })
  })

  it('derives barcode size', () => {
    expect(elementSizeMm({ type: 'barcode', x: 0, y: 0, width: 30, height: 10 })).toEqual({
      width: 30,
      height: 10,
    })
  })

  it('derives text height from font size', () => {
    expect(elementSizeMm({ type: 'text', x: 0, y: 0, content: 'x', font_size: 3 })).toEqual({
      width: 20,
      height: 3,
    })
  })
})

describe('元素越界处理', () => {
  it('leaves an in-bounds element untouched', () => {
    const { element, clipped } = clipToPaper({ type: 'qrcode', x: 10, y: 10, size: 10 }, doc)
    expect(clipped).toBe(false)
    expect(element).toMatchObject({ x: 10, y: 10, width: 10, height: 10 })
  })

  it('clips rather than scales at the right edge', () => {
    const { element, clipped } = clipToPaper({ type: 'qrcode', x: 55, y: 5, size: 20 }, doc)
    expect(clipped).toBe(true)
    expect(element.width).toBe(5)
    expect(element.height).toBe(20)
  })

  it('clips at the bottom edge', () => {
    const { element } = clipToPaper({ type: 'barcode', x: 0, y: 35, width: 20, height: 20 }, doc)
    expect(element.height).toBe(5)
  })

  it('pushes a negative origin back into the paper', () => {
    const { element, clipped } = clipToPaper({ type: 'qrcode', x: -5, y: -5, size: 10 }, doc)
    expect(clipped).toBe(true)
    expect(element.x).toBe(0)
    expect(element.y).toBe(0)
  })
})

describe('未知类型', () => {
  it('throws instead of skipping', () => {
    expect(() => elementSizeMm({ type: 'hologram', x: 0, y: 0 })).toThrow(RenderError)
  })

  it('throws from elementStyle too', () => {
    expect(() => elementStyle({ type: 'hologram', x: 0, y: 0 })).toThrow(RenderError)
  })
})

describe('动态字段', () => {
  it('reads the value from the payload', () => {
    expect(resolveFieldValue('batch_no', { batch_no: 'ALL20261012' })).toBe('ALL20261012')
  })

  it('renders an empty string when missing', () => {
    expect(resolveFieldValue('batch_no', {})).toBe('')
    expect(resolveFieldValue('batch_no', { batch_no: '' })).toBe('')
  })

  it('never renders the string null', () => {
    expect(resolveFieldValue('x', { x: null as unknown as string })).not.toBe('null')
  })
})

describe('字体回退', () => {
  it('puts the declared family first', () => {
    expect(fontFamilyChain('Arial').startsWith('Arial')).toBe(true)
  })

  it('always ends with the shared fallback chain', () => {
    expect(fontFamilyChain(undefined)).toBe('微软雅黑, monospace')
  })
})

describe('样式生成', () => {
  it('expresses font size in mm, not pt', () => {
    const style = elementStyle({ type: 'text', x: 1, y: 2, content: 'hi', font_size: 3 })
    expect(style.fontSize).toBe('3mm')
    expect(style.fontSize).not.toContain('pt')
  })

  it('uses mm for position and size', () => {
    const style = elementStyle({ type: 'qrcode', x: 3, y: 4, size: 12 })
    expect(style.left).toBe('3mm')
    expect(style.top).toBe('4mm')
    expect(style.width).toBe('12mm')
  })

  it('hides overflow', () => {
    expect(elementStyle({ type: 'text', x: 0, y: 0, content: 'x' }).overflow).toBe('hidden')
  })
})

describe('整份模板渲染', () => {
  const full: TemplateDoc = {
    paper_width_mm: 60,
    paper_height_mm: 40,
    elements: [
      { type: 'qrcode', x: 2, y: 2, size: 15 },
      { type: 'text', x: 20, y: 2, content: '产品：', font_size: 3 },
      { type: 'field', x: 20, y: 6, field_name: 'product_name', font_size: 3 },
      { type: 'field', x: 20, y: 10, field_name: 'batch_no', font_size: 3 },
    ],
  }

  it('resolves text and field elements', () => {
    const rendered = renderTemplate(full, {
      product_name: '500ml 矿泉水',
      batch_no: 'ALL202610120001',
    })
    expect(rendered[1].text).toBe('产品：')
    expect(rendered[2].text).toBe('500ml 矿泉水')
    expect(rendered[3].text).toBe('ALL202610120001')
  })

  it('gives image elements no text', () => {
    expect(renderTemplate(full, {})[0].text).toBeNull()
  })

  it('keeps every element inside the paper', () => {
    for (const { element } of renderTemplate(full, {})) {
      expect((element.x ?? 0) + (element.width ?? 0)).toBeLessThanOrEqual(doc.paper_width_mm)
    }
  })
})

describe('HTML 输出', () => {
  it('declares the exact paper size with zero margin', () => {
    const html = renderToString(doc, {})
    expect(html).toContain('@page')
    expect(html).toContain('60mm 40mm')
    expect(html).toContain('margin: 0')
  })

  it('escapes user-supplied text', () => {
    const html = renderToString(
      { ...doc, elements: [{ type: 'field', x: 0, y: 0, field_name: 'product_name' }] },
      { product_name: '<script>alert(1)</script>' },
    )
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })
})
