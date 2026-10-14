/**
 * 模板渲染规则（实现 contracts/template-rendering.md）。
 *
 * 宪章原则六规定两端代码 MUST NOT 交叉引用，因此工位端有一份**独立实现**
 * （print-client/src/print-render/renderer.ts）。两份实现必须对同一份契约，
 * 任何一端偏离契约都是缺陷——"所见即所打"全靠这个保证。
 */

/** 固定换算基准，不随屏幕 DPI 变化。 */
export const CSS_PX_PER_MM = 96 / 25.4

/** 打印侧缩放恒为 100%。 */
export const PRINT_SCALE_FACTOR = 100

export const ELEMENT_TYPES = ['qrcode', 'barcode', 'text', 'field'] as const
export type ElementType = (typeof ELEMENT_TYPES)[number]

export const FONT_FALLBACK = ['微软雅黑', 'monospace']

export interface TemplateElement {
  type: string
  x: number
  y: number
  size?: number
  width?: number
  height?: number
  content?: string
  field_name?: string
  font_size?: number
  font_family?: string
  bold?: boolean
  align?: 'left' | 'center' | 'right'
  /** 未知属性允许存在，便于向前兼容 */
  [key: string]: unknown
}

export interface TemplateDoc {
  paper_width_mm: number
  paper_height_mm: number
  elements: TemplateElement[]
}

export class RenderError extends Error {}

export function mmToPx(mm: number): number {
  return mm * CSS_PX_PER_MM
}

export function assertKnownType(type: string): ElementType {
  if (!(ELEMENT_TYPES as readonly string[]).includes(type)) {
    // 契约要求显式报错，MUST NOT 静默跳过——静默跳过会让标签少印一块而无人察觉
    throw new RenderError(`未识别的模板元素类型：${type}`)
  }
  return type as ElementType
}

/** 元素外接尺寸（毫米）。文本类元素高度由字号决定。 */
export function elementSizeMm(el: TemplateElement): { width: number; height: number } {
  switch (assertKnownType(el.type)) {
    case 'qrcode':
      return { width: el.size ?? 0, height: el.size ?? 0 }
    case 'barcode':
      return { width: el.width ?? 0, height: el.height ?? 0 }
    case 'text':
    case 'field':
      return { width: el.width ?? 0, height: el.font_size ?? 0 }
    default:
      return { width: 0, height: 0 }
  }
}

export interface ClippedElement {
  element: TemplateElement
  clipped: boolean
}

/**
 * 按纸张边界裁剪。
 *
 * 契约要求"超出部分被裁剪而非缩放"——缩放会改变已定义的版面，
 * 让同一份模板在不同纸张上印出不同比例。
 */
export function clipToPaper(el: TemplateElement, doc: TemplateDoc): ClippedElement {
  const { width, height } = elementSizeMm(el)
  const maxX = doc.paper_width_mm
  const maxY = doc.paper_height_mm

  const x = Math.max(0, Math.min(el.x, maxX))
  const y = Math.max(0, Math.min(el.y, maxY))
  const w = Math.max(0, Math.min(width, maxX - x))
  const h = Math.max(0, Math.min(height, maxY - y))

  const clipped = x !== el.x || y !== el.y || w !== width || h !== height
  return { element: { ...el, x, y, width: w, height: h }, clipped }
}

/** 动态字段取值。缺失时渲染空串，MUST NOT 渲染 "null" 或占位符。 */
export function resolveFieldValue(fieldName: string, data: Record<string, string>): string {
  const value = data[fieldName]
  return value === undefined || value === null ? '' : String(value)
}

/** 字体回退链：声明字体 -> 微软雅黑 -> monospace。两端 MUST 一致。 */
export function fontFamilyChain(family?: string): string {
  return [family, ...FONT_FALLBACK].filter(Boolean).join(', ')
}

/** 生成元素的内联样式（单位 mm，浏览器按 mm 排印再交给打印）。 */
export function elementStyle(el: TemplateElement): Record<string, string> {
  assertKnownType(el.type)
  const { width, height } = elementSizeMm(el)
  const align = el.align ?? 'left'

  const style: Record<string, string> = {
    position: 'absolute',
    left: `${el.x}mm`,
    top: `${el.y}mm`,
    width: `${width}mm`,
    height: `${height}mm`,
    textAlign: align,
    overflow: 'hidden',
    boxSizing: 'border-box',
  }

  if (el.type === 'text' || el.type === 'field') {
    style.fontSize = `${el.font_size ?? 0}mm` // 字号也是毫米，不是 pt
    style.fontFamily = fontFamilyChain(el.font_family)
    style.fontWeight = el.bold ? '700' : '400'
    style.lineHeight = '1'
  }

  return style
}

/** 把整份模板渲染成绝对定位的元素列表。 */
export function renderTemplate(
  doc: TemplateDoc,
  data: Record<string, string>,
): { element: TemplateElement; style: Record<string, string>; text: string | null }[] {
  return doc.elements.map((original) => {
    const { element } = clipToPaper(original, doc)
    const text =
      element.type === 'text'
        ? (element.content ?? '')
        : element.type === 'field'
          ? resolveFieldValue(element.field_name ?? '', data)
          : null
    return { element, style: elementStyle(element), text }
  })
}

/** 给 Element Plus / 打印用的纸张尺寸（毫米）。 */
export function paperSize(doc: TemplateDoc): { width: number; height: number } {
  return { width: doc.paper_width_mm, height: doc.paper_height_mm }
}
