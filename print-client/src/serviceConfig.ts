/** 开发版和安装版均连接已部署的 HTTPS 服务。 */
export const SERVICE_ORIGIN = 'https://lms.yuwangchenfa.com'

export interface ServiceRequest {
  path: string
  method: string
  headers: Record<string, string>
  body?: string
}

export interface ServiceResponse {
  status: number
  statusText: string
  body: string
}

export function serviceUrl(path: string): string {
  if (!path.startsWith('/api/v1/') || path.includes('\\')) throw new Error('无效的业务接口地址')
  const url = new URL(path, SERVICE_ORIGIN)
  if (url.origin !== SERVICE_ORIGIN || !url.pathname.startsWith('/api/v1/')) {
    throw new Error('无效的业务接口地址')
  }
  return url.href
}
