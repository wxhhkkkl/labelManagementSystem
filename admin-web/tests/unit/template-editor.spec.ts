/**
 * T120：模板编辑器的坐标与拖拽逻辑。
 *
 * 先写并运行至失败，再由 src/utils/templateEditor.ts 实现至通过。
 */

import { describe, expect, it } from 'vitest'
import { isProxy, reactive } from 'vue'

import {
  addElement,
  clampElement,
  cloneTemplateDoc,
  createElement,
  elementSummary,
  moveElement,
  moveElementTo,
  removeElement,
  rotateElement,
  typeLabel,
  updateElement,
  validateDocument,
} from '../../src/utils/templateEditor'
import type { TemplateDoc } from '../../src/utils/templateRender'

const doc: TemplateDoc = {
  paper_width_mm: 60,
  paper_height_mm: 40,
  elements: [{ type: 'qrcode', x: 10, y: 10, size: 15 }],
}

describe('cloneTemplateDoc', () => {
  it('copies nested reactive template data without sharing mutable state', () => {
    const source = reactive({
      ...doc,
      elements: reactive([
        reactive({ ...doc.elements[0], metadata: reactive({ label: '二维码' }) }),
      ]),
    })
    const copy = cloneTemplateDoc(source)
    expect(copy).toEqual(source)
    expect(isProxy(copy)).toBe(false)
    expect(isProxy(copy.elements[0].metadata)).toBe(false)
    copy.elements[0].x = 20
    ;(copy.elements[0].metadata as { label: string }).label = '副本'
    expect(source.elements[0].x).toBe(10)
    expect(source.elements[0].metadata.label).toBe('二维码')
  })
})

describe('clampElement', () => {
  it('leaves an in-bounds element alone', () => {
    const result = clampElement({ type: 'qrcode', x: 10, y: 10, size: 15 }, doc)
    expect(result.x).toBe(10)
    expect(result.y).toBe(10)
  })

  it('keeps the whole element on paper, not just its origin', () => {
    // 60 宽的纸上放 15mm 的二维码，x 最多 45——否则右边会被裁掉
    const result = clampElement({ type: 'qrcode', x: 55, y: 10, size: 15 }, doc)
    expect(result.x).toBe(45)
  })

  it('pulls a negative origin back to zero', () => {
    const result = clampElement({ type: 'qrcode', x: -5, y: -5, size: 15 }, doc)
    expect(result.x).toBe(0)
    expect(result.y).toBe(0)
  })

  it('clamps vertically too', () => {
    const result = clampElement({ type: 'qrcode', x: 0, y: 100, size: 15 }, doc)
    expect(result.y).toBe(25)
  })

  it('does not push an oversized element to a negative origin', () => {
    // 元素比纸还大时，只能落在 0 而不是负数
    const result = clampElement({ type: 'barcode', x: 5, y: 5, width: 200, height: 200 }, doc)
    expect(result.x).toBe(0)
    expect(result.y).toBe(0)
  })

  it('clamps using the rotated bounding box', () => {
    // 20×4 的文本旋转 90° 后占用 4×20，右边界按 4mm 计算
    const result = clampElement(
      { type: 'text', x: 58, y: 5, content: 'x', font_size: 3, width: 20, height: 4, rotate: 90 },
      doc,
    )
    expect(result.x).toBe(56)
  })
})

describe('rotateElement', () => {
  it('keeps the bounding-box center and swaps the footprint', () => {
    const input: TemplateDoc = {
      ...doc,
      elements: [{ type: 'text', x: 20, y: 15, content: 'x', font_size: 3, width: 20, height: 4 }],
    }
    const rotated = rotateElement(input, 0, 90).elements[0]
    expect(rotated.rotate).toBe(90)
    expect(rotated.x).toBe(28) // center 30 - 新宽度 4/2
    expect(rotated.y).toBe(7) // center 17 - 新高度 20/2
  })
})

describe('moveElement', () => {
  it('applies the delta', () => {
    const moved = moveElement({ type: 'qrcode', x: 0, y: 0, size: 15 }, 5, 3, doc)
    expect(moved).toEqual({ type: 'qrcode', x: 5, y: 3, size: 15 })
  })

  it('clamps when the move would leave the paper', () => {
    const moved = moveElement({ type: 'qrcode', x: 40, y: 0, size: 15 }, 50, 0, doc)
    expect(moved.x).toBe(45)
  })

  it('rounds to two decimals', () => {
    const moved = moveElement({ type: 'qrcode', x: 0, y: 0, size: 15 }, 1.23456, 0, doc)
    expect(moved.x).toBe(1.23)
  })
})

describe('createElement', () => {
  it('creates a qrcode with a sensible default size', () => {
    const el = createElement('qrcode', doc)
    expect(el.type).toBe('qrcode')
    expect(el.size).toBe(15)
  })

  it('rejects unknown types', () => {
    expect(() => createElement('hologram', doc)).toThrow()
  })

  it('creates a field with a valid default field name', () => {
    // 默认值必须是契约允许的四个字段之一，否则新建即非法
    expect(createElement('field', doc).field_name).toBe('code_value')
  })

  it('places new elements inside the paper', () => {
    const tiny: TemplateDoc = { paper_width_mm: 5, paper_height_mm: 5, elements: [] }
    const el = createElement('qrcode', tiny)
    expect(el.x).toBe(0)
    expect(el.y).toBe(0)
  })
})

describe('addElement / removeElement / updateElement', () => {
  it('appends without mutating the original', () => {
    const next = addElement(doc, 'text')
    expect(next.elements).toHaveLength(2)
    expect(doc.elements).toHaveLength(1)
  })

  it('removes by index', () => {
    const two = addElement(doc, 'text')
    expect(removeElement(two, 0).elements).toHaveLength(1)
  })

  it('ignores an out-of-range removal', () => {
    expect(removeElement(doc, 99)).toBe(doc)
  })

  it('patches an element and re-clamps it', () => {
    const patched = updateElement(doc, 0, { x: 999 })
    expect(patched.elements[0].x).toBe(45)
  })

  it('ignores an out-of-range update', () => {
    expect(updateElement(doc, 99, { x: 1 })).toBe(doc)
  })

  it('moves to an absolute position with clamping', () => {
    const moved = moveElementTo(doc, 0, 100, 100)
    expect(moved.elements[0].x).toBe(45)
    expect(moved.elements[0].y).toBe(25)
  })
})

describe('elementSummary / typeLabel', () => {
  it('summarises each element kind', () => {
    expect(elementSummary({ type: 'qrcode', x: 0, y: 0, size: 15 })).toContain('15')
    expect(elementSummary({ type: 'text', x: 0, y: 0, content: '产品' })).toContain('产品')
    expect(
      elementSummary({ type: 'field', x: 0, y: 0, field_name: 'batch_no', font_size: 3 }),
    ).toContain('batch_no')
  })

  it('translates type labels', () => {
    expect(typeLabel('qrcode')).toBe('二维码')
    expect(typeLabel('field')).toBe('动态字段')
    expect(typeLabel('unknown')).toBe('unknown')
  })
})

describe('validateDocument', () => {
  it('accepts a well-formed document', () => {
    expect(validateDocument(doc)).toEqual([])
  })

  it('flags a non-positive paper size', () => {
    expect(validateDocument({ ...doc, paper_width_mm: 0 }).length).toBeGreaterThan(0)
  })

  it('flags an element starting outside the paper', () => {
    const bad: TemplateDoc = {
      ...doc,
      elements: [{ type: 'qrcode', x: 200, y: 0, size: 15 }],
    }
    expect(validateDocument(bad).some((p) => p.includes('纸张之外'))).toBe(true)
  })

  it('flags an unknown element type', () => {
    const bad: TemplateDoc = { ...doc, elements: [{ type: 'hologram', x: 0, y: 0 }] }
    expect(validateDocument(bad).length).toBeGreaterThan(0)
  })

  it('flags a field without a field name', () => {
    const bad: TemplateDoc = { ...doc, elements: [{ type: 'field', x: 0, y: 0, font_size: 3 }] }
    expect(validateDocument(bad).some((p) => p.includes('动态字段名'))).toBe(true)
  })

  it('reports every problem rather than stopping at the first', () => {
    const bad: TemplateDoc = {
      paper_width_mm: 0,
      paper_height_mm: 0,
      elements: [{ type: 'field', x: 0, y: 0, font_size: 3 }],
    }
    expect(validateDocument(bad).length).toBeGreaterThanOrEqual(3)
  })
})
