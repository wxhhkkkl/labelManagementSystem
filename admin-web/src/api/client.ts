/**
 * 契约客户端。统一处理 Bearer 令牌与错误体（contracts/README.md 的统一错误响应）。
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

const TOKEN_KEY = 'lms.access_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
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
    if (resp.status === 401 && path !== '/api/v1/auth/login') {
      setToken(null)
      window.dispatchEvent(new Event('lms:unauthorized'))
    }
    const body: ApiErrorBody = payload ?? {
      error_code: 'UNKNOWN',
      message: resp.statusText,
      details: {},
    }
    throw new ApiError(resp.status, body)
  }
  return payload as T
}
