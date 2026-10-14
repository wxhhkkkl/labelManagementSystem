/** 看板与报表接口（contracts/admin-api.md 报表小节）。 */

import { downloadFile } from './import'
import { request } from './client'

export interface DistributionRow {
  key: string
  company_name: string | null
  product_name: string | null
  unallocated: number
  allocated: number
  printing: number
  printed: number
  voided: number
  allocated_not_printed: number
  total: number
}

export interface Distribution {
  group_by: string
  rows: DistributionRow[]
  totals: DistributionRow
}

export interface PrintDetail {
  code_value: string
  product_name: string | null
  company_name: string | null
  workstation_name: string | null
  operator_name: string | null
  printer_name: string
  print_type: string
  result: string
  failure_reason: string | null
  printed_at: string
}

export type GroupBy = 'company' | 'product' | 'company_product'

/** 收 object 而不是 Record：接口类型没有索引签名，直接传会报类型不兼容。 */
function query(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

export interface DistributionParams {
  group_by?: GroupBy
  created_from?: string
  created_to?: string
}

export const fetchDistribution = (params: DistributionParams = {}) =>
  request<Distribution>(`/api/v1/dashboard/code-distribution${query(params)}`)

export interface PrintDetailParams {
  company_id?: number
  workstation_id?: number
  operator_id?: number
  product_id?: number
  printed_from?: string
  printed_to?: string
  limit?: number
}

export const fetchPrintDetails = (params: PrintDetailParams = {}) =>
  request<PrintDetail[]>(`/api/v1/reports/prints${query(params)}`)

export const exportPrintDetails = (params: PrintDetailParams = {}) =>
  downloadFile(`/api/v1/reports/prints/export${query(params)}`, 'print-details.xlsx')

export const exportCodeStock = () =>
  downloadFile('/api/v1/reports/code-stock/export', 'code-stock.csv')
