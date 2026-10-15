/** 组织与账号接口（contracts/admin-api.md 组织与账号小节）。 */

import { request } from './client'
import type { Role } from '../utils/validate'

export interface Company {
  id: number
  code: string
  name: string
  contact: string | null
  region: string | null
  status: 'active' | 'disabled'
}

export interface Workstation {
  id: number
  code: string
  name: string
  company_id: number
  company_name: string | null
  printer_name: string | null
  status: 'active' | 'disabled'
  last_heartbeat_at: string | null
  online: boolean
  machine_bound?: boolean
  operator_ids: number[]
}

export interface OrgTreeNode {
  id: number
  code: string
  name: string
  status: 'active' | 'disabled'
  workstations: Workstation[]
}

export interface User {
  id: number
  username: string
  display_name: string
  role: Role
  company_id: number | null
  status: 'active' | 'disabled'
}

export const listCompanies = () => request<Company[]>('/api/v1/companies')

export const createCompany = (json: Partial<Company>) =>
  request<Company>('/api/v1/companies', { method: 'POST', json })

export const disableCompany = (id: number) =>
  request<Company>(`/api/v1/companies/${id}/disable`, { method: 'POST' })

export const getOrgTree = () => request<OrgTreeNode[]>('/api/v1/org/tree')

export const listWorkstations = (companyId?: number) =>
  request<Workstation[]>(
    `/api/v1/workstations${companyId ? `?company_id=${companyId}` : ''}`,
  )

export const createWorkstation = (json: Record<string, unknown>) =>
  request<Workstation>('/api/v1/workstations', { method: 'POST', json })

export const updateWorkstation = (id: number, json: Record<string, unknown>) =>
  request<Workstation>(`/api/v1/workstations/${id}`, { method: 'PATCH', json })

export const disableWorkstation = (id: number) =>
  request<Workstation>(`/api/v1/workstations/${id}/disable`, { method: 'POST' })

export const unbindWorkstation = (id: number) =>
  request<Workstation>(`/api/v1/workstations/${id}/unbind`, { method: 'POST' })

export const listUsers = (companyId?: number) =>
  request<User[]>(`/api/v1/users${companyId ? `?company_id=${companyId}` : ''}`)

export const createUser = (json: Record<string, unknown>) =>
  request<User>('/api/v1/users', { method: 'POST', json })

export const disableUser = (id: number) =>
  request<User>(`/api/v1/users/${id}/disable`, { method: 'POST' })
