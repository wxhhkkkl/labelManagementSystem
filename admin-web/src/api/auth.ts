/** 认证接口（contracts/auth-api.md）。 */

import { request } from './client'
import type { Role } from '../utils/validate'

export interface MeUser {
  id: number
  username: string
  display_name: string
  role: Role
  company_id: number | null
  company: { id: number; name: string } | null
  workstations: { id: number; name: string }[]
}

export const fetchMe = () => request<MeUser>('/api/v1/auth/me')

export const login = (username: string, password: string) =>
  request<{ access_token: string; refresh_token: string; expires_in: number; user: MeUser }>(
    '/api/v1/auth/login',
    { method: 'POST', json: { username, password } },
  )
