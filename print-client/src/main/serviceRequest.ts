import { serviceUrl, type ServiceRequest, type ServiceResponse } from '../serviceConfig'

/** 仅代理固定业务服务，避免 file:// 安装版和开发版受到浏览器跨域限制。 */
export async function requestService(
  request: ServiceRequest,
  transport: (url: string, init?: RequestInit) => Promise<Response>,
): Promise<ServiceResponse> {
  const url = serviceUrl(request.path)
  if (!['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method)) throw new Error('无效的请求方法')
  const headers = new Headers()
  for (const [key, value] of Object.entries(request.headers)) {
    if (!['authorization', 'content-type', 'x-lms-machine-id'].includes(key.toLowerCase())) {
      throw new Error('无效的请求头')
    }
    headers.set(key, value)
  }
  const response = await transport(url, {
    method: request.method, headers, body: request.body,
    redirect: 'error', credentials: 'omit', signal: AbortSignal.timeout(30000),
  })
  return { status: response.status, statusText: response.statusText, body: await response.text() }
}
