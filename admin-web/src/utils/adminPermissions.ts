export const SUB_ADMIN_PATHS = new Set([
  '/workstations',
  '/users',
  '/code-pool',
  '/code-actions',
  '/ledger',
  '/print-details',
])

export function canAccessAdminPage(role: string | undefined, path: string): boolean {
  if (!role) return false
  return role === 'sub_admin' ? SUB_ADMIN_PATHS.has(path) : role === 'hq_admin'
}

export function adminPageLabel(role: string | undefined, path: string, original: string): string {
  if (role !== 'sub_admin') return original
  if (path === '/users') return '员工管理'
  if (path === '/code-actions') return '码补打'
  if (path === '/ledger') return '补打明细'
  return original
}
