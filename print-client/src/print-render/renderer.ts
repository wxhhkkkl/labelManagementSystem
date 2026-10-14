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
      return { width: el.width ?? 0, height: el.font_size ?? 0 }
    default:
      return { width: 0, height: 0 }
  }
}

export interface ClippedElement {
  element: TemplateElement
  clipped: boolean
}

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

export function resolveFieldValue(fieldName: string, data: Record<string, string>): string {
  const value = data[fieldName]
  return value === undefined || value === null ? '' : String(value)
}

export function fontFamilyChain(family?: string): string {
  return [family, ...FONT_FALLBACK].filter(Boolean).join(', ')
}

export function elementStyle(el: TemplateElement): Record<string, string> {
  assertKnownType(el.type)
  const { width, height } = elementSizeMm(el)

  const style: Record<string, string> = {
    position: 'absolute',
    left: `${el.x}mm`,
    top: `${el.y}mm`,
    width: `${width}mm`,
    height: `${height}mm`,
    textAlign: el.align ?? 'left',
    overflow: 'hidden',
    boxSizing: 'border-box',
  }

  if (el.type === 'text' || el.type === 'field') {
    style.fontSize = `${el.font_size ?? 0}mm`
    style.fontFamily = fontFamilyChain(el.font_family)
    style.fontWeight = el.bold ? '700' : '400'
    style.lineHeight = '1'
  }

  return style
}

export interface RenderedElement {
  element: TemplateElement
  style: Record<string, string>
  text: string | null
}

export function renderTemplate(
  doc: TemplateDoc,
  data: Record<string, string>,
): RenderedElement[] {
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

export function paperSize(doc: TemplateDoc): { width: number; height: number } {
  return { width: doc.paper_width_mm, height: doc.paper_height_mm }
}

/**
 * 生成可直接交给 webContents.print 的整页 HTML。
 *
 * 用 `@page { size: Wmm Hmm; margin: 0 }` 把纸张尺寸交给浏览器排版，
 * 配合主进程固定 scaleFactor=100 实现"所见即所打"。
 */
export function renderToString(doc: TemplateDoc, data: Record<string, string>): string {
  const body = renderTemplate(doc, data)
    .map(({ element, style, text }) => {
      const css = Object.entries(style)
        .map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}:${v}`)
        .join(';')
      if (element.type === 'qrcode' || element.type === 'barcode') {
        // 图形元素由渲染层注入（二维码库/条码库），这里留出占位容器
        return `<div class="el ${element.type}" data-value="${escapeHtml(text ?? '')}" style="${css}"></div>`
      }
      return `<div class="el" style="${css}">${escapeHtml(text ?? '')}</div>`
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
