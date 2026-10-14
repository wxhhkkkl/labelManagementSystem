<template>
  <el-container class="app">
    <el-header class="header">
      <span class="title">打印管理系统 · 管理后台</span>
      <el-menu mode="horizontal" :default-active="active" router class="nav">
        <el-menu-item index="/org">组织树</el-menu-item>
        <el-menu-item index="/workstations">工位管理</el-menu-item>
        <el-menu-item index="/users">账号管理</el-menu-item>
        <el-menu-item index="/products">产品管理</el-menu-item>
        <el-menu-item index="/imports">码导入</el-menu-item>
        <el-menu-item index="/templates">模板管理</el-menu-item>
        <el-menu-item index="/allocations">码分配</el-menu-item>
        <el-menu-item index="/code-pool">码池</el-menu-item>
        <el-menu-item index="/code-actions">补打/作废</el-menu-item>
        <el-menu-item index="/ledger">补打作废台账</el-menu-item>
        <el-menu-item index="/dashboard">码量看板</el-menu-item>
        <el-menu-item index="/print-details">打印明细</el-menu-item>
        <el-menu-item index="/code-timeline">码追溯</el-menu-item>
        <el-menu-item index="/audit-logs">操作日志</el-menu-item>
      </el-menu>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const active = computed(() => route.path)
</script>

<style scoped>
.header {
  display: flex;
  align-items: center;
  gap: 24px;
  border-bottom: 1px solid var(--el-border-color);
}
.title {
  font-weight: 600;
}
.nav {
  flex: 1;
  border-bottom: none;
}
</style>
