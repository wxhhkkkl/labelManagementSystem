/**
 * T085（管理后台侧）：模板渲染换算。
 *
 * 这组用例直接对应 contracts/template-rendering.md 的"契约测试要求"表。
 * 工位端有一份独立实现，跑的是同一组用例——两端都过，才谈得上"所见即所打"。
 */

import { describe, expect, it } from 'vitest'

import {
  CSS_PX_PER_MM,
  PRINT_SCALE_FACTOR,
  RenderError,
  clipToPaper,
  elementBoundsMm,
  elementContentStyle,
  elementSizeMm,
  elementStyle,
  fontFamilyChain,
  mmToPx,
  renderTemplate,
  resolveFieldValue,
  type TemplateDoc,
} from '../../src/utils/templateRender'

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
    // 打印侧 MUST NOT 跟随系统 DPI 变化，否则同一模板在不同机器上印出不同尺寸
    expect(PRINT_SCALE_FACTOR).toBe(100)
  })
})

describe('元素尺寸', () => {
  it('derives qrcode size from the size attribute', () => {
    expect(elementSizeMm({ type: 'qrcode', x: 0, y: 0, size: 12 })).toEqual({
      width: 12,
      height: 12,
    })
  })

  it('derives barcode size from width and height', () => {
    expect(elementSizeMm({ type: 'barcode', x: 0, y: 0, width: 30, height: 10 })).toEqual({
      width: 30,
      height: 10,
    })
  })

  it('derives text height from font size in mm', () => {
    expect(elementSizeMm({ type: 'text', x: 0, y: 0, content: 'x', font_size: 3 })).toEqual({
      width: 20,
      height: 3,
    })
  })
})

describe('元素越界处理', () => {
  it('leaves an in-bounds element untouched', () => {
    const el = { type: 'qrcode', x: 10, y: 10, size: 10 }
    const { element, clipped } = clipToPaper(el, doc)
    expect(clipped).toBe(false)
    expect(element).toMatchObject({ x: 10, y: 10, size: 10 })
  })

  it('flags an element hanging off the right edge without scaling it', () => {
    const el = { type: 'qrcode', x: 55, y: 5, size: 20 }
    const { element, clipped } = clipToPaper(el, doc)
    expect(clipped).toBe(true)
    expect(element.x).toBe(55)
    expect(element.size).toBe(20) // 保持原尺寸，由纸张边界裁剪
  })

  it('flags an element beyond the bottom edge', () => {
    const el = { type: 'barcode', x: 0, y: 35, width: 20, height: 20 }
    const { element, clipped } = clipToPaper(el, doc)
    expect(clipped).toBe(true)
    expect(element.height).toBe(20)
  })

  it('pushes a negative origin back into the paper', () => {
    const el = { type: 'qrcode', x: -5, y: -5, size: 10 }
    const { element, clipped } = clipToPaper(el, doc)
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

  it('renders an empty string when the field is missing', () => {
    // 契约要求空串，MUST NOT 是 "null" / "undefined" / 占位符
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
    expect(fontFamilyChain()).toContain('微软雅黑')
    expect(fontFamilyChain()).toContain('monospace')
    expect(fontFamilyChain(undefined)).toBe('微软雅黑, monospace')
  })
})

describe('样式生成', () => {
  it('expresses font size in mm, not pt', () => {
    const style = elementContentStyle({ type: 'text', x: 1, y: 2, content: 'hi', font_size: 3 })
    expect(style.fontSize).toBe('3mm')
    expect(style.fontSize).not.toContain('pt')
  })

  it('swaps the bounding box for 90/270 and keeps the content centered', () => {
    const el = { type: 'text', x: 10, y: 5, content: 'x', font_size: 3, width: 20, height: 4 }
    expect(elementBoundsMm({ ...el, rotate: 0 })).toEqual({ width: 20, height: 4 })
    expect(elementBoundsMm({ ...el, rotate: 90 })).toEqual({ width: 4, height: 20 })
    expect(elementBoundsMm({ ...el, rotate: 180 })).toEqual({ width: 20, height: 4 })
    expect(elementBoundsMm({ ...el, rotate: 270 })).toEqual({ width: 4, height: 20 })
    expect(elementStyle({ ...el, rotate: 90 })).toMatchObject({
      left: '10mm',
      top: '5mm',
      width: '4mm',
      height: '20mm',
    })
    expect(elementContentStyle({ ...el, rotate: 90 })).toMatchObject({
      left: '-8mm',
      top: '8mm',
      width: '20mm',
      height: '4mm',
      transform: 'rotate(90deg)',
    })
  })

  it('uses mm for position and size', () => {
    const style = elementStyle({ type: 'qrcode', x: 3, y: 4, size: 12 })
    expect(style.left).toBe('3mm')
    expect(style.top).toBe('4mm')
    expect(style.width).toBe('12mm')
  })

  it('hides overflow so a too-long code cannot push the layout', () => {
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
    expect(rendered).toHaveLength(4)
    expect(rendered[1].text).toBe('产品：')
    expect(rendered[2].text).toBe('500ml 矿泉水')
    expect(rendered[3].text).toBe('ALL202610120001')
  })

  it('gives image elements no text', () => {
    const rendered = renderTemplate(full, {})
    expect(rendered[0].text).toBeNull()
  })

  it('keeps every element inside the paper', () => {
    const rendered = renderTemplate(full, {})
    for (const { element } of rendered) {
      const bounds = elementBoundsMm(element)
      expect(element.x ?? 0).toBeGreaterThanOrEqual(0)
      expect((element.x ?? 0) + bounds.width).toBeLessThanOrEqual(doc.paper_width_mm)
    }
  })
})
