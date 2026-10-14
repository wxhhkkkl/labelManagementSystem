/** 审计日志与码详情接口（contracts/admin-api.md）。 */

import { request } from './client'

export interface AuditLog {
  id: number
  operator_id: number
  role: string
  company_id: number | null
  workstation_id: number | null
  action: string
  target_type: string | null
  target_id: number | null
  ip: string | null
  result: string
  occurred_at: string
}

export interface TimelineEntry {
  event_type: string
  label: string
  from_status: string | null
  from_status_label: string | null
  to_status: string | null
  to_status_label: string | null
  operator_name: string | null
  workstation_name: string | null
  reason: string | null
  occurred_at: string
}

export interface CodeDetail {
  code_value: string
  status: string
  status_label: string
  product_name: string | null
  company_name: string | null
  allocation_order_no: string | null
  template_version_id: number | null
  print_count: number
  reprint_count: number
  void_reason: string | null
  timeline: TimelineEntry[]
}

export interface AuditFilters {
  role?: string
  company_id?: number
  action?: string
  result?: string
  occurred_from?: string
  occurred_to?: string
  limit?: number
  offset?: number
}

function query(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

export const listAuditLogs = (filters: AuditFilters = {}) =>
  request<AuditLog[]>(`/api/v1/audit-logs${query(filters)}`)

export const fetchCodeDetail = (codeValue: string) =>
  request<CodeDetail>(`/api/v1/codes/${encodeURIComponent(codeValue)}`)
