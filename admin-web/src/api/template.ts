/** 模板接口（contracts/admin-api.md 打印模板小节）。 */

import { request } from './client'
import type { TemplateDoc } from '../utils/templateRender'

export interface TemplateItem {
  id: number
  code: string
  name: string
  status: 'active' | 'disabled'
  current_version_no: number | null
  version_count: number
}

export interface TemplateVersionItem {
  id: number
  template_id: number
  version_no: number
  paper_width_mm: number
  paper_height_mm: number
  elements_json: TemplateDoc
  frozen: boolean
}

/** HTTP 头只能是 ASCII，密码按 Base64(UTF-8) 传输。 */
function encodeEditPassword(password: string): string {
  const bytes = new TextEncoder().encode(password)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

export const listTemplates = () => request<TemplateItem[]>('/api/v1/templates')

export const createTemplate = (json: Record<string, unknown>) =>
  request<TemplateItem>('/api/v1/templates', { method: 'POST', json })

export const addTemplateVersion = (templateId: number, doc: TemplateDoc, password: string) =>
  request<TemplateVersionItem>(`/api/v1/templates/${templateId}`, {
    method: 'PUT',
    headers: { 'X-Template-Edit-Password': encodeEditPassword(password) },
    json: {
      paper_width_mm: doc.paper_width_mm,
      paper_height_mm: doc.paper_height_mm,
      elements: doc.elements,
    },
  })

export const replaceTemplateVersion = (
  templateId: number,
  versionNo: number,
  doc: TemplateDoc,
  password: string,
) =>
  request<TemplateVersionItem>(`/api/v1/templates/${templateId}/versions/${versionNo}`, {
    method: 'PUT',
    headers: { 'X-Template-Edit-Password': encodeEditPassword(password) },
    json: {
      paper_width_mm: doc.paper_width_mm,
      paper_height_mm: doc.paper_height_mm,
      elements: doc.elements,
    },
  })

export const listTemplateVersions = (templateId: number) =>
  request<TemplateVersionItem[]>(`/api/v1/templates/${templateId}/versions`)

export const disableTemplate = (templateId: number) =>
  request<TemplateItem>(`/api/v1/templates/${templateId}/disable`, { method: 'POST' })
