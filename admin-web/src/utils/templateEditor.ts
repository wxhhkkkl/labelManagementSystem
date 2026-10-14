/**
 * 可视化模板编辑器的纯逻辑：拖拽边界、元素增删改。
 *
 * 与组件解耦以便单测覆盖（T120），也便于对照 contracts/template-rendering.md 检查：
 * 编辑器允许摆出的坐标，MUST 是渲染器接得住的范围。
 */

import { elementSizeMm, type TemplateDoc, type TemplateElement } from './templateRender'

export const CREATABLE_TYPES = ['qrcode', 'barcode', 'text', 'field'] as const

export const TYPE_LABELS: Record<string, string> = {
  qrcode: '二维码',
  barcode: '条码',
  text: '文本',
  field: '动态字段',
}

/** 新建元素的默认尺寸（毫米），保证建出来就在纸内且可见。 */
const DEFAULTS: Record<string, Partial<TemplateElement>> = {
  qrcode: { size: 15 },
  barcode: { width: 30, height: 10 },
  text: { content: '文本', font_size: 3, width: 20 },
  field: { field_name: 'code_value', font_size: 3, width: 20 },
}

export function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type
}

/**
 * 把元素夹到纸张范围内。
 *
 * 编辑器 MUST NOT 让管理员把元素拖到纸外——渲染端会裁剪掉，
 * 而"拖出去再拖回来"会让坐标悄悄丢失一部分。夹住更好：
 * 用户看到的就是最终印出来的位置。
 */
export function clampElement(el: TemplateElement, doc: TemplateDoc): TemplateElement {
  const { width, height } = elementSizeMm(el)
  const x = Math.max(0, Math.min(el.x, Math.max(0, doc.paper_width_mm - width)))
  const y = Math.max(0, Math.min(el.y, Math.max(0, doc.paper_height_mm - height)))
  return { ...el, x: round2(x), y: round2(y) }
}

function round2(value: number): number {
  return Math.round(value * 100) / 100
}

/** 拖动：先按位移算出新位置，再夹回纸内。 */
export function moveElement(
  el: TemplateElement,
  deltaXmm: number,
  deltaYmm: number,
  doc: TemplateDoc,
): TemplateElement {
  return clampElement({ ...el, x: el.x + deltaXmm, y: el.y + deltaYmm }, doc)
}

/** 追加一个带合理默认值的元素，位置放在纸张左上角留 2mm 边距处。 */
export function createElement(type: string, doc: TemplateDoc): TemplateElement {
  if (!(CREATABLE_TYPES as readonly string[]).includes(type)) {
    throw new Error(`不支持的元素类型：${type}`)
  }
  const base = { type, x: 2, y: 2, ...DEFAULTS[type] } as TemplateElement
  return clampElement(base, doc)
}

export function addElement(doc: TemplateDoc, type: string): TemplateDoc {
  return { ...doc, elements: [...doc.elements, createElement(type, doc)] }
}

export function removeElement(doc: TemplateDoc, index: number): TemplateDoc {
  if (index < 0 || index >= doc.elements.length) return doc
  return { ...doc, elements: doc.elements.filter((_, i) => i !== index) }
}

export function updateElement(
  doc: TemplateDoc,
  index: number,
  patch: Partial<TemplateElement>,
): TemplateDoc {
  if (index < 0 || index >= doc.elements.length) return doc
  return {
    ...doc,
    elements: doc.elements.map((el, i) =>
      i === index ? clampElement({ ...el, ...patch }, doc) : el,
    ),
  }
}

export function moveElementTo(doc: TemplateDoc, index: number, x: number, y: number): TemplateDoc {
  return updateElement(doc, index, { x, y })
}

/** 元素占位描述，用于列表展示。 */
export function elementSummary(el: TemplateElement): string {
  switch (el.type) {
    case 'qrcode':
      return `二维码 ${el.size ?? 0}mm`
    case 'barcode':
      return `条码 ${el.width ?? 0}×${el.height ?? 0}mm`
    case 'text':
      return `文本「${el.content ?? ''}」`
    case 'field':
      return `动态字段 ${el.field_name ?? ''}`
    default:
      return el.type
  }
}

/**
 * 编辑器整体校验：返回问题清单（空数组表示可保存）。
 *
 * 与服务端的 TemplateDoc 校验保持同一套规则——前端先拦一道，
 * 让管理员不必等一次往返才知道哪里的坐标填错了。
 */
export function validateDocument(doc: TemplateDoc): string[] {
  const problems: string[] = []

  if (!(doc.paper_width_mm > 0)) problems.push('纸张宽度必须大于 0')
  if (!(doc.paper_height_mm > 0)) problems.push('纸张高度必须大于 0')

  doc.elements.forEach((el, index) => {
    const label = `第 ${index + 1} 个元素（${typeLabel(el.type)}）`
    if (!(CREATABLE_TYPES as readonly string[]).includes(el.type)) {
      problems.push(`${label}：未识别的类型`)
      return
    }
    if (el.x < 0 || el.y < 0) {
      problems.push(`${label}：坐标不能为负`)
    }
    if (el.x >= doc.paper_width_mm || el.y >= doc.paper_height_mm) {
      problems.push(`${label}：起点已在纸张之外`)
    }
    if (el.type === 'field' && !el.field_name) {
      problems.push(`${label}：必须指定动态字段名`)
    }
  })

  return problems
}
