/** 补打、作废与台账接口（contracts/admin-api.md）。 */

import { request } from './client'

export interface ReprintTask {
  task_id: number
  code_value: string
  target_workstation_id: number
  target_workstation_name: string | null
  status: string
}

export interface VoidResult {
  voided: string[]
  skipped: string[]
}

export interface LedgerEntry {
  kind: string
  code_value: string
  product_name: string | null
  company_name: string | null
  reason: string | null
  operator_id: number | null
  workstation_id: number | null
  result: string | null
  occurred_at: string
}

export const requestReprint = (codeValue: string, reason: string) =>
  request<ReprintTask>(`/api/v1/codes/${encodeURIComponent(codeValue)}/reprint`, {
    method: 'POST',
    json: { reason },
  })

export const voidCodes = (codeValues: string[], reason: string) =>
  request<VoidResult>('/api/v1/codes/void', {
    method: 'POST',
    json: { code_values: codeValues, reason },
  })

export const listLedger = (limit = 200) =>
  request<LedgerEntry[]>(`/api/v1/reprints?limit=${limit}`)
