/** 工位软件侧接口（contracts/workstation-api.md）。 */

import { request, setBoundWorkstationId } from './client'

export interface BindResponse {
  workstation_id: number
  name: string
  company_id: number
  printer_name: string | null
}

export interface MeUser {
  id: number
  username: string
  display_name: string
  role: string
  company_id: number | null
  company: { id: number; name: string } | null
  workstations: { id: number; name: string }[]
}

export const login = (username: string, password: string) =>
  request<{ access_token: string; user: MeUser }>('/api/v1/auth/login', {
    method: 'POST',
    json: { username, password },
  })

export const fetchMe = () => request<MeUser>('/api/v1/auth/me')

/** 声明本机代表的工位；成功后把绑定关系写入本机存储。 */
export async function bindWorkstation(workstationId: number): Promise<BindResponse> {
  const result = await request<BindResponse>('/api/v1/workstation/bind', {
    method: 'POST',
    json: { workstation_id: workstationId },
  })
  setBoundWorkstationId(result.workstation_id)
  return result
}

export const sendHeartbeat = (workstationId: number, printServiceOk = true) =>
  request<void>('/api/v1/workstation/heartbeat', {
    method: 'POST',
    json: { workstation_id: workstationId, print_service_ok: printServiceOk },
  })


/** 保存本工位默认打印机（FR-070）。 */
export const setWorkstationPrinter = (workstationId: number, printerName: string) =>
  request<{ workstation_id: number; printer_name: string | null }>(
    '/api/v1/workstation/printer',
    {
      method: 'PUT',
      json: { workstation_id: workstationId, printer_name: printerName },
    },
  )
