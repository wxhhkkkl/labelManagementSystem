/** 码导入接口（contracts/admin-api.md 码导入小节）。 */

import { getToken, request } from './client'

export interface ImportBatch {
  id: number
  batch_no: string
  code_list_filename: string
  mapping_filename: string
  product_id?: number | null
  product_names?: string[]
  status: string
  total_rows: number | null
  processed_rows: number
  success_count: number
  failure_count: number
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface ImportCreated {
  batch_id: number
  batch_no: string
  status: string
}

export const listBatches = () => request<ImportBatch[]>('/api/v1/imports')

export const getBatch = (id: number) => request<ImportBatch>(`/api/v1/imports/${id}`)

/** 上传两个文件。走 multipart，不能用 client.request 的 json 通道。 */
export async function uploadImport(
  codeListFile: File,
  mappingFile: File | null,
  productId?: number,
): Promise<ImportCreated> {
  const form = new FormData()
  form.append('code_list_file', codeListFile)
  if (mappingFile) form.append('mapping_file', mappingFile)
  if (productId !== undefined) form.append('product_id', String(productId))

  const { ApiError } = await import('./client')
  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const resp = await fetch('/api/v1/imports', { method: 'POST', body: form, headers })
  const payload = await resp.json().catch(() => null)
  if (!resp.ok) {
    throw new ApiError(
      resp.status,
      payload ?? { error_code: 'UNKNOWN', message: resp.statusText, details: {} },
    )
  }
  return payload as ImportCreated
}

/** 下载模板 / 失败明细需要带令牌，因此用 fetch + blob 而不是直接开链接。 */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const resp = await fetch(path, { headers })
  if (!resp.ok) {
    const payload = await resp.json().catch(() => null)
    const { ApiError } = await import('./client')
    throw new ApiError(
      resp.status,
      payload ?? { error_code: 'UNKNOWN', message: resp.statusText, details: {} },
    )
  }

  const blob = await resp.blob()
  const disposition = resp.headers.get('content-disposition') ?? ''
  const matched = /filename="?([^"]+)"?/.exec(disposition)
  const name = matched?.[1] ?? fallbackName

  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export const downloadTemplate = () =>
  downloadFile('/api/v1/imports/template', 'import-template.xlsx')

export const downloadErrors = (batchId: number, batchNo: string) =>
  downloadFile(`/api/v1/imports/${batchId}/errors`, `${batchNo}-errors.csv`)
