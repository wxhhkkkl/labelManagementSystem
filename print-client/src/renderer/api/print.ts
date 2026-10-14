/** T097：工位端打印接口客户端（contracts/workstation-api.md）。 */

import type { TemplateDoc } from '../../print-render/renderer'
import { request } from './client'

export interface PrintableCode {
  code_value: string
  product_id: number
}

export interface PrintableCodePage {
  total: number
  items: PrintableCode[]
  screen_scope_note: string
}

export interface AcceptedPrint {
  code_value: string
  template_version_id: number
  elements_json: TemplateDoc
  data: Record<string, string>
}

export interface RejectedPrint {
  code_value: string
  error_code: string
  message: string
}

export interface PrintResponse {
  accepted: AcceptedPrint[]
  rejected: RejectedPrint[]
}

export interface ConfirmItem {
  code_value: string
  outcome: 'succeeded' | 'failed'
  printer_name?: string | null
  failure_reason?: string | null
}

export interface ConfirmResponse {
  confirmed: string[]
  rejected: RejectedPrint[]
}

export const listPrintableCodes = (
  workstationId: number,
  productId: number,
  page = 1,
  pageSize = 100,
) =>
  request<PrintableCodePage>(
    `/api/v1/workstation/codes?workstation_id=${workstationId}&product_id=${productId}` +
      `&page=${page}&page_size=${pageSize}`,
  )

export const scanCode = (workstationId: number, codeValue: string) =>
  request<{ code_value: string; product_id: number; status: string }>(
    `/api/v1/workstation/codes/${encodeURIComponent(codeValue)}?workstation_id=${workstationId}`,
  )

/** 预占：返回可打印的模板与数据，以及被拒的码（逐码独立）。 */
export const startPrint = (
  workstationId: number,
  codeValues: string[],
  printerName?: string,
) =>
  request<PrintResponse>('/api/v1/workstation/print', {
    method: 'POST',
    json: {
      workstation_id: workstationId,
      code_values: codeValues,
      printer_name: printerName ?? null,
    },
  })

export const confirmPrint = (workstationId: number, results: ConfirmItem[]) =>
  request<ConfirmResponse>('/api/v1/workstation/print/confirm', {
    method: 'POST',
    json: { workstation_id: workstationId, results },
  })
