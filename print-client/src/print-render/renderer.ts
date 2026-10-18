import { qrcode, code128, code39, ean13, drawingSVG } from '@bwip-js/generic'

/**
 * 模板渲染规则（实现 contracts/template-rendering.md）。
 *
 * ⚠️ 这是**独立实现**，不是管理后台那份的引用。宪章原则六规定两端代码
 * MUST NOT 交叉引用，所以同一套规则在这里重新实现一遍。
 *
 * 代价是同一规则维护两份；收益是两端可以独立发布、独立升级。
 * 两份实现跑的是同一组契约用例（tests/unit/render.spec.ts），
 * 任何一端偏离契约都会在测试里暴露。
 *
 * 打印侧的额外要求：缩放恒为 100%，不跟随系统 DPI。
 */

export const CSS_PX_PER_MM = 96 / 25.4

/** 打印侧缩放恒为 100%（契约第 2 节）。 */
export const PRINT_SCALE_FACTOR = 100

export const ELEMENT_TYPES = ['qrcode', 'barcode', 'text', 'field', 'date', 'serial'] as const
export type ElementType = (typeof ELEMENT_TYPES)[number]

export const FONT_FALLBACK = ['微软雅黑', 'monospace']

export interface TemplateElement {
  type: string
  x: number
  y: number
  /** 顺时针旋转角度；x/y 是旋转后外接框的左上角。 */
  rotate?: number
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
    // 契约要求显式报错，MUST NOT 静默跳过
    throw new RenderError(`未识别的模板元素类型：${type}`)
  }
  return type as ElementType
}

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

/** 旋转后占用的外接框尺寸；90/270 时宽高互换。 */
export function elementBoundsMm(el: TemplateElement): { width: number; height: number } {
  const { width, height } = elementSizeMm(el)
  const angle = ((el.rotate ?? 0) % 360 + 360) % 360
  return angle === 90 || angle === 270
    ? { width: height, height: width }
    : { width, height }
}

export interface ClippedElement {
  element: TemplateElement
  clipped: boolean
}

export function clipToPaper(el: TemplateElement, doc: TemplateDoc): ClippedElement {
  const { width, height } = elementBoundsMm(el)
  const maxX = doc.paper_width_mm
  const maxY = doc.paper_height_mm

  const x = Math.max(0, Math.min(el.x, maxX))
  const y = Math.max(0, Math.min(el.y, maxY))
  const clipped = x !== el.x || y !== el.y || x + width > maxX || y + height > maxY
  return { element: { ...el, x, y }, clipped }
}

export function resolveFieldValue(fieldName: string, data: Record<string, string>): string {
  const value = data[fieldName]
  return value === undefined || value === null ? '' : String(value)
}

export function fontFamilyChain(family?: string): string {
  return [family, ...FONT_FALLBACK].filter(Boolean).join(', ')
}

/** 元素外接框的定位样式（单位 mm）。 */
export function elementStyle(el: TemplateElement): Record<string, string> {
  assertKnownType(el.type)
  const { width, height } = elementBoundsMm(el)
  return {
    position: 'absolute',
    left: `${el.x}mm`,
    top: `${el.y}mm`,
    width: `${width}mm`,
    height: `${height}mm`,
    overflow: 'hidden',
    boxSizing: 'border-box',
  }
}

/** 外接框内的内容样式：按未旋转尺寸居中，再绕中心旋转。 */
export function elementContentStyle(el: TemplateElement): Record<string, string> {
  assertKnownType(el.type)
  const bounds = elementBoundsMm(el)
  const { width, height } = elementSizeMm(el)
  const angle = el.rotate ?? 0
  const style: Record<string, string> = {
    position: 'absolute',
    left: `${(bounds.width - width) / 2}mm`,
    top: `${(bounds.height - height) / 2}mm`,
    width: `${width}mm`,
    height: `${height}mm`,
    textAlign: el.align ?? 'left',
    overflow: 'hidden',
    boxSizing: 'border-box',
    transformOrigin: 'center center',
  }
  if (angle) style.transform = `rotate(${angle}deg)`

  if (['text', 'field', 'date', 'serial'].includes(el.type)) {
    style.fontSize = `${el.font_size ?? 0}mm`
    style.fontFamily = fontFamilyChain(el.font_family)
    style.fontWeight = el.bold ? '700' : '400'
    style.lineHeight = el.height ? '1.2' : '1'
    style.whiteSpace = el.multiline ? 'pre-wrap' : 'nowrap'
  }

  return style
}

export interface RenderedElement {
  element: TemplateElement
  style: Record<string, string>
  contentStyle: Record<string, string>
  text: string | null
}

export function renderTemplate(doc: TemplateDoc, data: Record<string, string>): RenderedElement[] {
  return doc.elements.map((original) => {
    const { element } = clipToPaper(original, doc)
    const text = ['qrcode', 'barcode'].includes(element.type) ? null : elementText(element, data)
    return {
      element,
      style: elementStyle(original),
      contentStyle: elementContentStyle(original),
      text,
    }
  })
}

export function paperSize(doc: TemplateDoc): { width: number; height: number } {
  return { width: doc.paper_width_mm, height: doc.paper_height_mm }
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

/**
 * 生成可直接交给 webContents.print 的整页 HTML。
 *
 * 用 `@page { size: Wmm Hmm; margin: 0 }` 把纸张尺寸交给浏览器排版，
 * 配合主进程固定 scaleFactor=100 实现"所见即所打"。
 */
export function renderToString(doc: TemplateDoc, data: Record<string, string>): string {
  for (const el of doc.elements) {
    if (
      (el.type === 'serial' || (el.type === 'date' && el.date_source !== 'fixed')) &&
      !elementText(el, data)
    ) {
      throw new RenderError('缺少服务端的首次打印日期或流水号，拒绝打印空白字段')
    }
  }
  const body = renderTemplate(doc, data)
    .map(({ element, style, contentStyle, text }) => {
      const css = (values: Record<string, string>) =>
        Object.entries(values)
          .map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}:${v}`)
          .join(';')
      const inner =
        element.type === 'qrcode' || element.type === 'barcode'
          ? `<img alt="" src="${escapeHtml(graphicDataUrl(element, data))}" style="width:100%;height:100%;object-fit:fill" />`
          : escapeHtml(text ?? '')
      return `<div class="el-wrap ${element.type}" style="${escapeHtml(css(style))}"><div class="el" style="${escapeHtml(css(contentStyle))}">${inner}</div></div>`
    })
    .join('')

  return `<!doctype html>
<html><head><meta charset="utf-8" />
<style>
  @page { size: ${doc.paper_width_mm}mm ${doc.paper_height_mm}mm; margin: 0; }
  html, body { margin: 0; padding: 0; width: ${doc.paper_width_mm}mm; height: ${doc.paper_height_mm}mm; }
  .el { white-space: nowrap; }
</style></head>
<body>${body}</body></html>`
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
