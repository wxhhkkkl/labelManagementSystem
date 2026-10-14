<template>
  <div>
    <h2>补打 / 作废台账</h2>
    <p class="hint">供审计使用：每条记录都带必填原因与操作人。子公司只能看到本公司的记录。</p>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="toolbar">
      <el-radio-group v-model="kindFilter">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="reprint">补打</el-radio-button>
        <el-radio-button value="void">作废</el-radio-button>
      </el-radio-group>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="filtered" border size="small">
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-tag :type="row.kind === 'void' ? 'danger' : 'warning'" size="small">
            {{ ledgerKindLabel(row.kind) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="code_value" label="码值" width="220" />
      <el-table-column prop="product_name" label="产品" />
      <el-table-column label="公司" width="150">
        <template #default="{ row }">{{ row.company_name ?? '总部码池' }}</template>
      </el-table-column>
      <el-table-column prop="reason" label="原因" />
      <el-table-column label="操作人" width="100">
        <template #default="{ row }">{{ row.operator_id ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.kind === 'reprint'" size="small" type="info">
            {{ taskStatusLabel(row.result ?? '') }}
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">{{ formatTime(row.occurred_at) }}</template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !filtered.length" description="暂无补打或作废记录" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import { listLedger, type LedgerEntry } from '../../api/reprint'
import { ledgerKindLabel, taskStatusLabel } from '../../utils/reprint'

const entries = ref<LedgerEntry[]>([])
const kindFilter = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

const filtered = computed(() =>
  kindFilter.value ? entries.value.filter((e) => e.kind === kindFilter.value) : entries.value,
)

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    entries.value = await listLedger()
  } catch (e) {
    error.value = e instanceof ApiError ? e.body.message : '加载台账失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
}
</style>
