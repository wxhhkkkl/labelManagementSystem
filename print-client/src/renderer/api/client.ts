/**
 * 工位软件的契约客户端。
 *
 * 宪章原则六：本文件是 print-client 自己的实现，MUST NOT 从 admin-web 引入任何代码。
 * 业务数据一律经 HTTP 接口获取，工位软件 MUST NOT 直接访问服务端数据库（FR-076）。
 */

export interface ApiErrorBody {
  error_code: string
  message: string
  details: Record<string, unknown>
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiErrorBody,
  ) {
    super(body.message)
  }
}

const ACCESS_TOKEN_KEY = 'lms.workstation.access_token'
const WORKSTATION_KEY = 'lms.workstation.bound_id'
const PRINTER_KEY = 'lms.workstation.printer'

/** 绑定关系持久化在本机（FR-069）；令牌应存 Electron safeStorage，此处为渲染层缓存。 */
export function getToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(ACCESS_TOKEN_KEY, token)
  else localStorage.removeItem(ACCESS_TOKEN_KEY)
}

export function getBoundWorkstationId(): number | null {
  const raw = localStorage.getItem(WORKSTATION_KEY)
  return raw ? Number(raw) : null
}

export function setBoundWorkstationId(id: number | null): void {
  if (id === null) localStorage.removeItem(WORKSTATION_KEY)
  else localStorage.setItem(WORKSTATION_KEY, String(id))
}

/** 本工位绑定的打印机名。存在本机——它描述的是这台电脑的硬件。 */
export function getBoundPrinter(): string | null {
  return localStorage.getItem(PRINTER_KEY)
}

export function setBoundPrinter(name: string | null): void {
  if (name === null) localStorage.removeItem(PRINTER_KEY)
  else localStorage.setItem(PRINTER_KEY, name)
}

export async function request<T>(
  path: string,
  options: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, ...init } = options
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (json !== undefined) headers.set('Content-Type', 'application/json')

  const resp = await fetch(path, {
    ...init,
    headers,
    body: json !== undefined ? JSON.stringify(json) : init.body,
  })

  if (resp.status === 204) return undefined as T

  const payload = await resp.json().catch(() => null)
  if (!resp.ok) {
    throw new ApiError(
      resp.status,
      payload ?? { error_code: 'UNKNOWN', message: resp.statusText, details: {} },
    )
  }
  return payload as T
}
