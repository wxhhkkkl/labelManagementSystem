<template>
  <div class="station-shell">
    <header class="station-header">
      <div class="brand"><img class="app-logo" :src="logoUrl" alt="标签打印系统 Logo" /><div>标签管理系统<small>工位打印端</small></div></div>
      <div v-if="user" class="station-identity session-identity">
        <strong>{{ user.display_name }}（{{ user.username }}）</strong>
        <span>{{ user.company?.name ?? '未关联企业' }} · {{ boundName || '待绑定工位' }}</span>
      </div>
      <span v-else class="station-identity">请操作员登录</span>
      <button v-if="user" class="logout-button" @click="logout">退出登录</button>
    </header>
      <nav class="station-tabs" aria-label="工位导航">
        <button :class="{ active: tab === 'print' }" @click="tab = 'print'">{{ workstationId ? '工位打印' : '操作员登录' }}</button>
        <button v-if="workstationId" :class="{ active: tab === 'settings' }" @click="tab = 'settings'">工位状态</button>
        <button :class="{ active: tab === 'drivers' }" @click="tab = 'drivers'">打印机驱动安装</button>
      </nav>
    <BindWorkstationView v-if="!workstationId && tab !== 'drivers'" :session-user="user" @bound="onBound" />
      <main v-if="workstationId || tab === 'drivers'" class="station-content">
        <PrintView v-if="workstationId" v-show="tab === 'print'" />
        <SettingsView v-if="tab === 'settings' && workstationId" :workstation-id="workstationId" />
        <DriverInstallView v-if="tab === 'drivers'" :bound="!!workstationId" @settings="tab = workstationId ? 'settings' : 'print'" />
        <footer class="app-footer"><span>标签管理系统 · 工位打印端</span><span>模板由后台统一配置</span></footer>
      </main>
  </div>
</template>
<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { setToken } from './api/client'
import type { MeUser, BindResponse } from './api/workstation'
import BindWorkstationView from './views/BindWorkstationView.vue'
import PrintView from './views/PrintView.vue'
import SettingsView from './views/SettingsView.vue'
import DriverInstallView from './views/DriverInstallView.vue'
const logoUrl = new URL('../../resources/app-logo.svg', import.meta.url).href

// Machine bindings persist; operator sessions are established on every launch.
setToken(null)
const user = ref<MeUser | null>(null)
const boundName = ref('')
const workstationId = ref<number | null>(null)
const tab = ref<'print' | 'settings' | 'drivers'>('print')
function onBound(id: number, profile: MeUser, station: BindResponse): void {
  workstationId.value = id
  user.value = profile
  boundName.value = station.name
}
function logout(): void {
  setToken(null)
  user.value = null
  workstationId.value = null
  boundName.value = ''
  tab.value = 'print'
}
function bindingInvalid(): void { workstationId.value = null; boundName.value = ''; tab.value = 'print' }
onMounted(() => window.addEventListener('lms:binding-invalid', bindingInvalid))
onUnmounted(() => window.removeEventListener('lms:binding-invalid', bindingInvalid))
</script>
