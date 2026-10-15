import { qrcode, code128, code39, ean13, drawingSVG } from '@bwip-js/generic'

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

export const ELEMENT_TYPES = ['qrcode', 'barcode', 'text', 'field', 'date', 'serial'] as const
export type ElementType = (typeof ELEMENT_TYPES)[number]

export const FONT_FALLBACK = ['微软雅黑', 'monospace']

export interface TemplateElement {
  type: string
  x: number
  y: number
  size?: number
  width?: number
  height?: number
  ec_level?: string
  symbology?: string
  show_text?: boolean
  date_format?: string
  date_source?: string
  prefix?: string
  suffix?: string
  serial_digits?: number
  multiline?: boolean
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
    case 'date':
    case 'serial':
      return { width: el.width ?? 20, height: el.height ?? el.font_size ?? 3 }
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

  if (['text', 'field', 'date', 'serial'].includes(el.type)) {
    style.fontSize = `${el.font_size ?? 0}mm` // 字号也是毫米，不是 pt
    style.fontFamily = fontFamilyChain(el.font_family)
    style.fontWeight = el.bold ? '700' : '400'
    style.lineHeight = el.height ? '1.2' : '1'
    style.whiteSpace = el.multiline ? 'pre-wrap' : 'nowrap'
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
    const text = ['qrcode', 'barcode'].includes(element.type) ? null : elementText(element, data)
    return { element, style: elementStyle(original), text }
  })
}

/** 日期和编号使用服务端下发的快照；渲染端不会自行递增或读取系统日期。 */
export function elementText(el: TemplateElement, data: Record<string, string>): string {
  if (el.type === 'date') {
    const value =
      el.date_source === 'fixed' ? (el.content ?? '') : resolveFieldValue('print_date', data)
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return ''
    const date = new Date(value + 'T00:00:00Z')
    if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value) return ''
    const [year, month, day] = value.split('-')
    return (el.date_format ?? 'YYYY-MM-DD').replace(
      /YYYY|YY|MM|DD/g,
      (token) => ({ YYYY: year, YY: year.slice(-2), MM: month, DD: day })[token] ?? '',
    )
  }
  if (el.type === 'serial') {
    const value = resolveFieldValue('serial_no', data)
    if (!value) return ''
    return (el.prefix ?? '') + value.padStart(el.serial_digits ?? 6, '0') + (el.suffix ?? '')
  }
  if (el.type === 'text') return el.content ?? ''
  if (el.type === 'field') return resolveFieldValue(el.field_name ?? '', data)
  return el.field_name
    ? resolveFieldValue(el.field_name, data)
    : (el.content ?? resolveFieldValue('code_value', data))
}

const graphicCache = new Map<string, string>()

/** 本地生成真实 SVG，不向外部条码服务发送业务码值。 */
export function graphicSvg(el: TemplateElement, data: Record<string, string>): string {
  const value = elementText(el, data)
  if (!value) throw new RenderError('二维码或条码内容不能为空')
  const key = JSON.stringify([el.type, value, el.ec_level, el.symbology, el.show_text])
  const cached = graphicCache.get(key)
  if (cached) return cached
  const remember = (svg: string) => {
    if (graphicCache.size >= 100) graphicCache.clear()
    graphicCache.set(key, svg)
    return svg
  }
  try {
    const draw = drawingSVG()
    if (el.type === 'qrcode') {
      const options = {
        bcid: 'qrcode',
        text: value,
        eclevel: el.ec_level ?? 'M',
        padding: 4,
        backgroundcolor: 'FFFFFF',
      }
      return remember(qrcode(options, draw))
    }
    const encoders = { code128, code39, ean13 }
    const kind = (el.symbology ?? 'code128') as keyof typeof encoders
    if (!encoders[kind]) throw new RenderError('不支持的条码制式')
    return remember(
      encoders[kind](
        {
          bcid: kind,
          text: value,
          height: 10,
          includetext: el.show_text ?? false,
          textxalign: 'center',
          padding: 3,
          backgroundcolor: 'FFFFFF',
        },
        draw,
      ),
    )
  } catch (error) {
    throw new RenderError(
      '图形编码失败：' + (error instanceof Error ? error.message : String(error)),
    )
  }
}

export function graphicDataUrl(el: TemplateElement, data: Record<string, string>): string {
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(graphicSvg(el, data))
}

/** 给 Element Plus / 打印用的纸张尺寸（毫米）。 */
export function paperSize(doc: TemplateDoc): { width: number; height: number } {
  return { width: doc.paper_width_mm, height: doc.paper_height_mm }
}
