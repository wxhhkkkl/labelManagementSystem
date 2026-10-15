/**
 * 本地打印服务的客户端（回环 HTTP）。
 *
 * 界面与打印服务之间的通信限于本机回环，**不承载业务数据**——
 * 业务数据一律走服务端 HTTP 接口（FR-076）。
 */

import type { TemplateDoc } from '../../print-render/renderer'
import { renderToString } from '../../print-render/renderer'

interface Bridge {
  machineId: string
  printServicePort: number
  printServiceToken: string
}

declare global {
  interface Window {
    lmsBridge?: Bridge
  }
}

export class PrintServiceUnavailable extends Error {}

function baseUrl(): string {
  const port = window.lmsBridge?.printServicePort ?? 0
  if (!port) throw new PrintServiceUnavailable('本地打印服务未启动')
  return `http://127.0.0.1:${port}`
}

function token(): string {
  return window.lmsBridge?.printServiceToken ?? ''
}

/** 健康检查不需要令牌——它正是用来判断服务在不在。 */
export async function isPrintServiceAlive(): Promise<boolean> {
  try {
    const resp = await fetch(`${baseUrl()}/health`, { method: 'GET' })
    return resp.ok
  } catch {
    return false
  }
}

export async function listPrinters(): Promise<string[]> {
  const resp = await fetch(`${baseUrl()}/printers`, {
    headers: { 'X-Print-Token': token() },
  })
  if (!resp.ok) throw new PrintServiceUnavailable('无法获取本机打印机列表')
  const body = (await resp.json()) as { printers: string[] }
  return body.printers ?? []
}

export interface PrintRequest {
  doc: TemplateDoc
  data: Record<string, string>
  deviceName: string
}

export async function getDefaultPrinter(): Promise<string | null> {
  const response = await fetch(`${baseUrl()}/default-printer`, { headers: { 'X-Print-Token': token() } })
  if (!response.ok) throw new PrintServiceUnavailable('无法读取系统默认打印机')
  const data = await response.json() as { printer: string | null }
  return data.printer
}

export async function print(
  request: PrintRequest,
): Promise<{ ok: boolean; error?: string }> {
  const html = renderToString(request.doc, request.data)
  const resp = await fetch(`${baseUrl()}/print`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Print-Token': token() },
    body: JSON.stringify({
      html,
      deviceName: request.deviceName,
      pageSize: { width: request.doc.paper_width_mm, height: request.doc.paper_height_mm },
    }),
  })
  const body = (await resp.json()) as { ok?: boolean; error?: string }
  return { ok: resp.ok && body.ok !== false, error: body.error }
}
