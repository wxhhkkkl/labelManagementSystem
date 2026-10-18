/**
 * 可视化模板编辑器的纯逻辑：拖拽边界、元素增删改。
 *
 * 与组件解耦以便单测覆盖（T120），也便于对照 contracts/template-rendering.md 检查：
 * 编辑器允许摆出的坐标，MUST 是渲染器接得住的范围。
 */

import {
  elementBoundsMm,
  graphicSvg,
  type TemplateDoc,
  type TemplateElement,
} from './templateRender'

export const CREATABLE_TYPES = ['qrcode', 'barcode', 'text', 'field', 'date', 'serial'] as const

/** 模板是接口中的 JSON 文档；通过 JSON 复制兼容 Vue 的嵌套响应式代理。 */
export function cloneTemplateDoc(doc: TemplateDoc): TemplateDoc {
  return JSON.parse(JSON.stringify(doc)) as TemplateDoc
}

export const TYPE_LABELS: Record<string, string> = {
  qrcode: '二维码',
  barcode: '条码',
  text: '文本',
  field: '动态字段',
  date: '日期',
  serial: '流水号',
}

/** 新建元素的默认尺寸（毫米），保证建出来就在纸内且可见。 */
const DEFAULTS: Record<string, Partial<TemplateElement>> = {
  qrcode: { size: 15, field_name: 'code_value', ec_level: 'M' },
  barcode: {
    width: 30,
    height: 10,
    field_name: 'code_value',
    symbology: 'code128',
    show_text: false,
  },
  text: { content: '文本', font_size: 3, width: 20, height: 4.2 },
  field: { field_name: 'code_value', font_size: 3, width: 30, height: 4.2 },
  date: { date_source: 'print', date_format: 'YYYY-MM-DD', font_size: 3, width: 25, height: 4.2 },
  serial: { prefix: '', suffix: '', serial_digits: 6, font_size: 3, width: 25, height: 4.2 },
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
  const { width, height } = elementBoundsMm(el)
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

/** 旋转元素：外接框中心保持不动，再夹回纸张内。 */
export function rotateElement(doc: TemplateDoc, index: number, angle: number): TemplateDoc {
  if (index < 0 || index >= doc.elements.length) return doc
  const el = doc.elements[index]
  const oldBounds = elementBoundsMm(el)
  const cx = el.x + oldBounds.width / 2
  const cy = el.y + oldBounds.height / 2
  const rotated = { ...el, rotate: ((angle % 360) + 360) % 360 }
  const bounds = elementBoundsMm(rotated)
  return {
    ...doc,
    elements: doc.elements.map((item, i) =>
      i === index
        ? clampElement(
            {
              ...rotated,
              x: round2(cx - bounds.width / 2),
              y: round2(cy - bounds.height / 2),
            },
            doc,
          )
        : item,
    ),
  }
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
    case 'date':
      return `日期 ${el.date_format ?? 'YYYY-MM-DD'}`
    case 'serial':
      return `${el.prefix ?? ''}${'1'.padStart(el.serial_digits ?? 6, '0')}${el.suffix ?? ''}`
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

  if (!(doc.paper_width_mm > 0 && doc.paper_width_mm <= 500)) problems.push('纸张宽度必须大于 0')
  if (!(doc.paper_height_mm > 0 && doc.paper_height_mm <= 500)) problems.push('纸张高度必须大于 0')

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
    if (![0, 90, 180, 270].includes(el.rotate ?? 0)) {
      problems.push(`${label}：旋转角度只能是 0/90/180/270`)
    }
    const size = elementBoundsMm(el)
    if (![el.x, el.y, size.width, size.height].every(Number.isFinite))
      problems.push(`${label}：位置和尺寸必须为有效数字`)
    if (!(size.width > 0) || !(size.height > 0)) problems.push(`${label}：宽度和高度必须大于 0`)
    if (['text', 'field', 'date', 'serial'].includes(el.type) && !(Number(el.font_size) > 0))
      problems.push(`${label}：字号必须大于 0`)
    if (
      el.type === 'date' &&
      el.date_source === 'fixed' &&
      (!el.content ||
        !/^\d{4}-\d{2}-\d{2}$/.test(el.content) ||
        Number.isNaN(Date.parse(el.content)) ||
        new Date(el.content).toISOString().slice(0, 10) !== el.content)
    )
      problems.push(`${label}：请选择有效的固定日期`)
    if (
      el.type === 'serial' &&
      (!Number.isInteger(el.serial_digits ?? 6) ||
        Number(el.serial_digits ?? 6) < 1 ||
        Number(el.serial_digits ?? 6) > 12)
    )
      problems.push(`${label}：流水号位数应为 1 至 12`)
    if (el.type === 'qrcode' || el.type === 'barcode') {
      if (
        el.field_name &&
        ![
          'code_value',
          'product_name',
          'company_name',
          'batch_no',
          'production_batch_no',
          'print_date',
          'serial_no',
        ].includes(el.field_name)
      )
        problems.push(`${label}：未知的绑定字段`)
      if (
        el.type === 'barcode' &&
        !['code128', 'code39', 'ean13'].includes(el.symbology ?? 'code128')
      )
        problems.push(`${label}：不支持的条码制式`)
      // 动态内容按每个码的实际值校验，不能用预览样例限制可保存的模板。
      if (!el.field_name && el.content != null) {
        try {
          graphicSvg(el, {})
        } catch (error) {
          problems.push(`${label}：${error instanceof Error ? error.message : String(error)}`)
        }
      }
    }
    if (el.type === 'field' && !el.field_name) {
      problems.push(`${label}：必须指定动态字段名`)
    }
  })

  return problems
}
