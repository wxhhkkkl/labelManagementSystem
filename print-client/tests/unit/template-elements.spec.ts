import { describe, expect, it } from 'vitest'
import {
  renderToString,
  elementText,
  graphicSvg,
  renderTemplate,
  elementSizeMm,
} from '../../src/print-render/renderer'

describe('日期、流水号与图形内容', () => {
  it('formats the stored first-print date, independent of the client clock', () => {
    const el = { type: 'date', x: 0, y: 0, date_format: 'YYYY年MM月DD日' }
    expect(elementText(el, { print_date: '2026-10-14' })).toBe('2026年10月14日')
    expect(elementText({ ...el, date_format: 'YY-MM-DD' }, { print_date: '2026-10-12' })).toBe('26-10-12')
    expect(elementText(el, {})).toBe('')
    expect(elementText({ ...el, date_source: 'fixed', content: '2026-02-01' }, {})).toBe(
      '2026年02月01日',
    )
  })
  it('pads daily numbers without truncating and keeps prefix and suffix', () => {
    const el = { type: 'serial', x: 0, y: 0, serial_digits: 4, prefix: 'SN-', suffix: '-A' }
    expect(elementText(el, { serial_no: '12' })).toBe('SN-0012-A')
    expect(elementText(el, { serial_no: '12345' })).toBe('SN-12345-A')
    expect(elementText(el, {})).toBe('')
  })
  it('encodes fixed or dynamic content as real SVG symbols', () => {
    const el = { type: 'qrcode', x: 0, y: 0, size: 15, field_name: 'code_value' }
    expect(graphicSvg(el, { code_value: 'ABC123' })).toContain('<svg')
    expect(graphicSvg(el, { code_value: 'ABC123' })).toContain('<path')
    expect(graphicSvg(el, { code_value: 'ABC123' })).not.toEqual(
      graphicSvg(el, { code_value: 'XYZ456' }),
    )
    expect(
      graphicSvg({ type: 'barcode', x: 0, y: 0, symbology: 'code128', content: '123456' }, {}),
    ).toContain('<path')
    expect(() => graphicSvg({ ...el, field_name: undefined, content: '' }, {})).toThrow(
      '内容不能为空',
    )
  })
  it('clips at the paper edge without shrinking the encoded symbol', () => {
    const el = { type: 'qrcode', x: 55, y: 0, size: 15 }
    const rendered = renderTemplate(
      { paper_width_mm: 60, paper_height_mm: 40, elements: [el] },
      {},
    )[0]
    expect(rendered.element.width).toBe(5)
    expect(rendered.style.width).toBe('15mm')
  })
  it('keeps explicit text box height and newline formatting', () => {
    const el = {
      type: 'text',
      x: 0,
      y: 0,
      width: 30,
      height: 12,
      font_size: 3,
      content: '第一行\n第二行',
      multiline: true,
    }
    expect(elementSizeMm(el)).toEqual({ width: 30, height: 12 })
    const rendered = renderTemplate(
      { paper_width_mm: 60, paper_height_mm: 40, elements: [el] },
      {},
    )[0]
    expect(rendered.style.whiteSpace).toBe('pre-wrap')
  })
})

it('print HTML contains encoded images and refuses missing identity data', () => {
  const doc = {
    paper_width_mm: 60,
    paper_height_mm: 40,
    elements: [{ type: 'qrcode', x: 0, y: 0, size: 15 }],
  }
  expect(renderToString(doc, { code_value: 'ABC123' })).toContain('data:image/svg+xml')
  expect(() =>
    renderToString({ ...doc, elements: [{ type: 'serial', x: 0, y: 0, font_size: 3 }] }, {}),
  ).toThrow('拒绝打印空白字段')
})
