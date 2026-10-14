<template>
  <div>
    <h2>组织树</h2>
    <p class="hint">公司的工位按公司汇总展示，可下钻查看（FR-008）。</p>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <el-tree
      v-loading="loading"
      :data="tree"
      node-key="key"
      :props="{ label: 'label', children: 'children' }"
      default-expand-all
      class="tree"
    />

    <el-empty v-if="!loading && !tree.length" description="尚未建立任何公司" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import { getOrgTree, type OrgTreeNode } from '../../api/org'

const nodes = ref<OrgTreeNode[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

interface TreeNode {
  key: string
  label: string
  children?: TreeNode[]
}

const tree = computed<TreeNode[]>(() =>
  nodes.value.map((company) => ({
    key: `company-${company.id}`,
    label: `${company.name}（${company.code}）${company.status === 'disabled' ? ' · 已停用' : ''}`,
    children: company.workstations.map((ws) => ({
      key: `ws-${ws.id}`,
      label: `${ws.name}（${ws.code}）· ${ws.online ? '在线' : '离线'} · ${
        ws.printer_name ?? '未绑定打印机'
      }`,
    })),
  })),
)

onMounted(async () => {
  loading.value = true
  try {
    nodes.value = await getOrgTree()
  } catch (e) {
    error.value = e instanceof ApiError ? e.body.message : '加载组织树失败'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.tree {
  margin-top: 12px;
}
</style>
