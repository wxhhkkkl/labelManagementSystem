<template>
  <div>
    <h2>操作日志</h2>
    <p class="hint">
      仅总部管理员可查。日志只增不改不删——系统里根本没有修改或删除日志的入口。
    </p>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="toolbar">
      <el-select v-model="filters.role" placeholder="角色" clearable @change="reload">
        <el-option label="总部管理员" value="hq_admin" />
        <el-option label="子公司管理员" value="sub_admin" />
        <el-option label="工位操作员" value="operator" />
      </el-select>

      <el-select v-model="filters.result" placeholder="结果" clearable @change="reload">
        <el-option label="成功" value="success" />
        <el-option label="被拒" value="denied" />
        <el-option label="失败" value="failed" />
      </el-select>

      <el-input
        v-model="filters.action"
        placeholder="按操作类型模糊匹配"
        clearable
        style="width: 220px"
        @keyup.enter="reload"
      />

      <el-button @click="reload">查询</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border size="small">
      <el-table-column label="时间" width="180">
        <template #default="{ row }">{{ formatTime(row.occurred_at) }}</template>
      </el-table-column>
      <el-table-column prop="action" label="操作" width="180" />
      <el-table-column label="角色" width="130">
        <template #default="{ row }">{{ roleLabel(row.role) }}</template>
      </el-table-column>
      <el-table-column prop="operator_id" label="操作人" width="90" />
      <el-table-column label="对象" width="240">
        <template #default="{ row }">
          {{ row.target_type ?? '—' }}{{ row.target_id ? `#${row.target_id}` : '' }}
        </template>
      </el-table-column>
      <el-table-column label="结果" width="90">
        <template #default="{ row }">
          <el-tag :type="resultTag(row.result)" size="small">{{ resultLabel(row.result) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="IP" width="140" />
    </el-table>

    <el-pagination
      class="pager"
      layout="prev, pager, next"
      :page-size="pageSize"
      :total="hasMore ? (page + 2) * pageSize : (page + 1) * pageSize"
      :current-page="page + 1"
      @current-change="onPage"
    />

    <el-empty v-if="!loading && !rows.length" description="没有符合条件的日志" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import { listAuditLogs, type AuditFilters, type AuditLog } from '../../api/audit'

const pageSize = 200

const rows = ref<AuditLog[]>([])
const filters = ref<AuditFilters>({})
const page = ref(0)
const hasMore = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)

function roleLabel(role: string): string {
  return (
    { hq_admin: '总部管理员', sub_admin: '子公司管理员', operator: '工位操作员' }[role] ?? role
  )
}

function resultTag(result: string): 'success' | 'danger' | 'warning' {
  if (result === 'success') return 'success'
  if (result === 'denied') return 'warning'
  return 'danger'
}

function resultLabel(result: string): string {
  return { success: '成功', denied: '被拒', failed: '失败' }[result] ?? result
}

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const batch = await listAuditLogs({
      ...filters.value,
      limit: pageSize,
      offset: page.value * pageSize,
    })
    rows.value = batch
    // 只有拿满一页才可能还有下一页，避免为一个不存在的下一页做无谓请求
    hasMore.value = batch.length === pageSize
  } catch (e) {
    error.value = e instanceof ApiError ? e.body.message : '加载操作日志失败'
  } finally {
    loading.value = false
  }
}

function reload(): void {
  page.value = 0
  void load()
}

function onPage(next: number): void {
  page.value = next - 1
  void load()
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
  flex-wrap: wrap;
}
.pager {
  margin-top: 12px;
}
</style>
