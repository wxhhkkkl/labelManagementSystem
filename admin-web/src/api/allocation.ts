/** 分配、回收与码池接口（contracts/admin-api.md）。 */

import { request } from './client'

export interface AllocationOrder {
  id: number
  order_no: string
  production_batch_no?: string | null
  company_id: number
  company_name: string | null
  product_id: number
  product_name: string | null
  code_count: number
  code_range_from: string | null
  code_range_to: string | null
  template_version_id: number
  template_name?: string | null
  allocated_by: number
  allocated_at: string
  status: 'active' | 'reclaimed'
}

export interface AllocationCreated {
  order: AllocationOrder
  allocated: number
}

export interface CodeItem {
  id: number
  code_value: string
  production_batch_no?: string | null
  status: string
  product_id: number
  company_id: number | null
  import_batch_id: number
  print_count: number
  reprint_count: number
}

export interface CodePage {
  items: CodeItem[]
  total: number
  page: number
  page_size: number
}

export interface CodeFilters {
  product_id?: number
  status?: string
  batch_id?: number
  company_id?: number
  page?: number
  page_size?: number
}

function query(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

export const listAllocations = (companyId?: number) =>
  request<AllocationOrder[]>(`/api/v1/allocations${query({ company_id: companyId })}`)

export const createAllocation = (json: Record<string, unknown>) =>
  request<AllocationCreated>('/api/v1/allocations', { method: 'POST', json })

export const reclaimAllocation = (orderId: number) =>
  request<AllocationOrder>(`/api/v1/allocations/${orderId}/reclaim`, { method: 'POST' })

export const listCodes = (filters: CodeFilters = {}) =>
  request<CodePage>(`/api/v1/codes${query({ ...filters })}`)
