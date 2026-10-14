import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/org' },
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
