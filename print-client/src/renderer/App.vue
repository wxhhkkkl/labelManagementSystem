<template>
  <!-- 未绑定工位时强制先完成首次配置（FR-069），绑定后进入打印界面 -->
  <BindWorkstationView v-if="!workstationId" @bound="onBound" />

  <template v-else>
    <nav class="tabs">
      <button :class="{ active: tab === 'print' }" @click="tab = 'print'">打印</button>
      <button :class="{ active: tab === 'settings' }" @click="tab = 'settings'">设置</button>
    </nav>
    <PrintView v-if="tab === 'print'" />
    <SettingsView v-else :workstation-id="workstationId" />
  </template>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import { getBoundWorkstationId } from './api/client'
import BindWorkstationView from './views/BindWorkstationView.vue'
import PrintView from './views/PrintView.vue'
import SettingsView from './views/SettingsView.vue'

const workstationId = ref<number | null>(getBoundWorkstationId())
const tab = ref<'print' | 'settings'>('print')

function onBound(id: number): void {
  workstationId.value = id
}
</script>

<style scoped>
.tabs {
  display: flex;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid #e4e7ed;
}
.tabs button {
  padding: 6px 16px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 14px;
}
.tabs button.active {
  font-weight: 600;
  border-bottom: 2px solid #409eff;
}
</style>

<style>
body {
  margin: 0;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
}
</style>
