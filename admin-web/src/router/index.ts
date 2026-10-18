import { createRouter, createWebHistory } from 'vue-router'
import { fetchMe } from '../api/auth'
import { ApiError, getToken, setToken } from '../api/client'
import { canAccessAdminPage } from '../utils/adminPermissions'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/auth/LoginView.vue'),
    },
    { path: '/', redirect: '/org' },
    { path: '/help', name: 'user-manual', component: () => import('../views/help/UserManualView.vue') },
    {
      path: '/org',
      name: 'org-tree',
      component: () => import('../views/org/OrgTreeView.vue'),
    },
    {
      path: '/workstations',
      name: 'workstations',
      component: () => import('../views/org/WorkstationListView.vue'),
    },
    {
      path: '/users',
      name: 'users',
      component: () => import('../views/org/UserListView.vue'),
    },
    {
      path: '/products',
      name: 'products',
      component: () => import('../views/product/ProductListView.vue'),
    },
    {
      path: '/imports',
      name: 'imports',
      component: () => import('../views/import/ImportView.vue'),
    },
    {
      path: '/allocations',
      name: 'allocations',
      component: () => import('../views/allocation/AllocationView.vue'),
    },
    {
      path: '/code-pool',
      name: 'code-pool',
      component: () => import('../views/allocation/CodePoolView.vue'),
    },
    {
      path: '/code-actions',
      name: 'code-actions',
      component: () => import('../views/code/CodeActionsPanel.vue'),
    },
    {
      path: '/ledger',
      name: 'ledger',
      component: () => import('../views/report/ReprintLedgerView.vue'),
    },
    {
      path: '/templates',
      name: 'templates',
      component: () => import('../views/template/TemplateListView.vue'),
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('../views/dashboard/DashboardView.vue'),
    },
    {
      path: '/print-details',
      name: 'print-details',
      component: () => import('../views/report/PrintDetailView.vue'),
    },
    {
      path: '/code-timeline',
      name: 'code-timeline',
      component: () => import('../views/code/CodeTimelineView.vue'),
    },
    {
      path: '/audit-logs',
      name: 'audit-logs',
      component: () => import('../views/audit/AuditLogView.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  if (to.name === 'login') return true
  const loginRoute = { name: 'login', query: { redirect: to.fullPath } }
  if (!getToken()) return loginRoute
  try {
    const user = await fetchMe()
    if (!canAccessAdminPage(user.role, to.path)) {
      return user.role === 'sub_admin' ? '/workstations' : '/login'
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      setToken(null)
      return loginRoute
    }
    // 网络或服务错误由业务页面展示，保留现有登录状态。
  }
  return true
})

window.addEventListener('lms:unauthorized', () => {
  if (router.currentRoute.value.name !== 'login') {
    void router.replace({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
  }
})
