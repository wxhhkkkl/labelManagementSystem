<template>
  <router-view v-if="route.name === 'login'" />
  <div v-else class="admin-shell">
    <button v-if="menuOpen" class="menu-backdrop" aria-label="关闭导航" @click="menuOpen = false" />
    <aside class="admin-sidebar" :class="{ open: menuOpen }">
      <div class="brand">
        <span class="brand-mark">L</span>
        <div>标签管理系统<small>LABEL MANAGEMENT</small></div>
      </div>
      <nav aria-label="后台导航">
        <section v-for="group in visibleGroups" :key="group.label">
          <p v-if="group.label !== '工作空间'" class="nav-group">{{ group.label }}</p>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            :class="{ selected: route.path === item.path }"
            @click="menuOpen = false"
            ><el-icon class="nav-icon" aria-hidden="true"><component :is="item.icon" /></el-icon
            >{{ item.label }}</router-link
          >
        </section>
      </nav>
      <div class="sidebar-foot">标签管理 · 工位协同 · 全程追溯</div>
    </aside>
    <div class="admin-workarea">
      <header class="admin-topbar">
        <div class="breadcrumb">
          <el-button class="menu-toggle" aria-label="展开导航" @click="menuOpen = !menuOpen"
            >菜单</el-button
          ><span>{{ currentGroup }}</span
          ><span class="separator">/</span><strong>{{ currentTitle }}</strong>
        </div>
        <div class="user-actions">
          <router-link class="help-shortcut" to="/help">使用说明</router-link>
          <span class="user-avatar">{{ user?.display_name?.slice(0, 1) || '管' }}</span
          ><span>{{ user?.display_name || '管理后台' }}</span
          ><el-button text type="primary" @click="logout">退出登录</el-button>
        </div>
      </header>
      <main class="admin-main">
        <div class="business-page"><router-view /></div>
        <footer class="app-footer">
          <span>标签管理系统</span><span>统一码管理 · 打印与追溯</span>
        </footer>
      </main>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataAnalysis,
  Share,
  Monitor,
  User,
  Box,
  DocumentCopy,
  Upload,
  Switch,
  Coin,
  RefreshLeft,
  Tickets,
  Printer,
  Search,
  Document,
} from '@element-plus/icons-vue'
import { fetchMe, type MeUser } from './api/auth'
import { setToken } from './api/client'
import { canAccessAdminPage, adminPageLabel } from './utils/adminPermissions'
const route = useRoute()
const router = useRouter()
const menuOpen = ref(false)
const user = ref<MeUser | null>(null)
const groups = [
  { label: '工作空间', items: [{ path: '/dashboard', label: '码量看板', icon: DataAnalysis }] },
  {
    label: '基础管理',
    items: [
      { path: '/org', label: '组织树', icon: Share },
      { path: '/workstations', label: '工位管理', icon: Monitor },
      { path: '/users', label: '账号管理', icon: User },
      { path: '/products', label: '产品管理', icon: Box },
      { path: '/templates', label: '模板管理', icon: DocumentCopy },
    ],
  },
  {
    label: '码与打印',
    items: [
      { path: '/imports', label: '码导入', icon: Upload },
      { path: '/allocations', label: '码分配', icon: Switch },
      { path: '/code-pool', label: '码池查询', icon: Coin },
      { path: '/code-actions', label: '补打与作废', icon: RefreshLeft },
      { path: '/ledger', label: '补打作废台账', icon: Tickets },
      { path: '/print-details', label: '打印明细', icon: Printer },
      { path: '/code-timeline', label: '码追溯', icon: Search },
      { path: '/audit-logs', label: '操作日志', icon: Document },
    ],
  },
  { label: '帮助中心', items: [{ path: '/help', label: '使用说明', icon: Document }] },
]
const currentGroup = computed(
  () =>
    groups.find((group) => group.items.some((item) => item.path === route.path))?.label ||
    '管理后台',
)
const visibleGroups = computed(() =>
  groups
    .map((group) => ({
      ...group,
      items: group.items
        .filter((item) => canAccessAdminPage(user.value?.role, item.path))
        .map((item) => ({
          ...item,
          label: adminPageLabel(user.value?.role, item.path, item.label),
        })),
    }))
    .filter((group) => group.items.length),
)
const currentTitle = computed(
  () =>
    visibleGroups.value.flatMap((group) => group.items).find((item) => item.path === route.path)
      ?.label || '管理后台',
)
watch(
  () => route.name,
  async (name) => {
    if (!name || name === 'login') {
      user.value = null
      return
    }
    try {
      user.value = await fetchMe()
    } catch {
      /* 业务页面继续展示接口错误 */
    }
  },
  { immediate: true },
)
function logout() {
  setToken(null)
  user.value = null
  void router.replace('/login')
}
</script>
<style scoped>
.admin-shell {
  display: flex;
  min-height: 100vh;
}
.help-shortcut { color:var(--lms-blue); text-decoration:none; white-space:nowrap; }
.admin-sidebar {
  position: sticky;
  top: 0;
  height: 100dvh;
  align-self: flex-start;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  width: 218px;
  flex-shrink: 0;
  padding: 16px;
  background: #fff;
  border-right: 1px solid var(--lms-line);
}
.admin-sidebar nav { margin-top: 12px; }
.nav-group {
  color: #8394ad;
  font-size: 11px;
  padding: 10px 12px 4px;
  line-height: 16px;
  margin: 0;
}
nav a {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  color: #536680;
  padding: 6px 13px;
  border-radius: 8px;
  margin: 1px 0;
  font-size: 13px;
  line-height: 20px;
}
nav a:hover,
nav a.selected {
  color: var(--lms-blue);
  background: var(--lms-soft);
}
nav a.selected {
  font-weight: 600;
}
.nav-icon {
  font-size: 18px;
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}
.sidebar-foot {
  margin-top: 10px;
  padding: 6px 8px;
  font-size: 11px;
  color: var(--lms-muted);
}
.admin-workarea {
  flex: 1;
  min-width: 0;
}
.admin-topbar {
  min-height: 76px;
  background: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 16px 32px;
  border-bottom: 1px solid var(--lms-line);
}
.breadcrumb,
.user-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}
.breadcrumb {
  color: var(--lms-muted);
}
.breadcrumb strong {
  color: var(--lms-ink);
  font-weight: 500;
}
.separator {
  color: #b5c1d3;
}
.user-avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  color: var(--lms-blue);
  background: var(--lms-soft);
}
.admin-main {
  padding: 30px 32px 20px;
  max-width: 1800px;
  margin: auto;
}
.menu-toggle,
.menu-backdrop {
  display: none;
}
@media (max-width: 900px) {
  .admin-sidebar {
    width: 190px;
    padding: 16px 12px;
  }
  .admin-main {
    padding: 24px 20px;
  }
  .admin-topbar {
    padding: 16px 20px;
  }
}
@media (max-height: 800px) {
  .admin-sidebar { padding-top: 12px; padding-bottom: 12px; }
  .admin-sidebar nav { margin-top: 8px; }
  .nav-group { padding-top: 7px; padding-bottom: 3px; }
  nav a { padding-top: 5px; padding-bottom: 5px; margin: 0; }
  .sidebar-foot { display: none; }
}
@media (max-width: 640px) {
  .admin-sidebar {
    display: none;
  }
  .admin-sidebar.open {
    display: block;
    position: fixed;
    z-index: 100;
    inset: 0 auto 0 0;
    width: 240px;
    overflow: auto;
  }
  .menu-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 99;
    background: #172b4d66;
    border: 0;
  }
  .menu-toggle {
    display: inline-flex;
  }
  .admin-topbar {
    padding: 12px;
    flex-wrap: wrap;
  }
  .admin-main {
    padding: 20px 12px;
  }
  .user-actions {
    margin-left: auto;
  }
  .breadcrumb {
    gap: 8px;
  }
}
</style>
