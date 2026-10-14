<template>
  <div>
    <h2>码全生命周期追溯</h2>
    <p class="hint">输入任一码值，查看它从导入到当前状态的完整时间线。</p>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="toolbar">
      <el-input
        v-model="codeValue"
        placeholder="输入或扫码定位码值"
        style="width: 340px"
        clearable
        @keyup.enter="search"
      />
      <el-button type="primary" :loading="loading" @click="search">查询</el-button>
    </div>

    <template v-if="detail">
      <el-descriptions :column="3" border class="summary">
        <el-descriptions-item label="码值">{{ detail.code_value }}</el-descriptions-item>
        <el-descriptions-item label="当前状态">
          <el-tag :type="statusTag(detail.status)" size="small">{{ detail.status_label }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="产品">{{ detail.product_name ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="归属公司">
          {{ detail.company_name ?? '总部码池' }}
        </el-descriptions-item>
        <el-descriptions-item label="分配单">
          {{ detail.allocation_order_no ?? '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="打印 / 补打次数">
          {{ detail.print_count }} / {{ detail.reprint_count }}
        </el-descriptions-item>
        <el-descriptions-item v-if="detail.void_reason" label="作废原因" :span="3">
          {{ detail.void_reason }}
        </el-descriptions-item>
      </el-descriptions>

      <el-timeline class="timeline">
        <el-timeline-item
          v-for="(entry, index) in detail.timeline"
          :key="index"
          :timestamp="formatTime(entry.occurred_at)"
          placement="top"
          :type="entryColor(entry.event_type)"
        >
          <div class="entry">
            <span class="entry-label">{{ entry.label }}</span>
            <span v-if="entry.from_status_label || entry.to_status_label" class="transition">
              {{ entry.from_status_label ?? '—' }} → {{ entry.to_status_label ?? '—' }}
            </span>
          </div>
          <div class="meta">
            <span v-if="entry.operator_name">操作人：{{ entry.operator_name }}</span>
            <span v-if="entry.workstation_name">工位：{{ entry.workstation_name }}</span>
            <span v-if="entry.reason">原因：{{ entry.reason }}</span>
          </div>
        </el-timeline-item>
      </el-timeline>

      <el-empty v-if="!detail.timeline.length" description="该码还没有产生任何事件" />
    </template>

    <el-empty v-else-if="!loading && searched" description="未找到该码" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import { ApiError } from '../../api/client'
import { fetchCodeDetail, type CodeDetail } from '../../api/audit'

const codeValue = ref('')
const detail = ref<CodeDetail | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const searched = ref(false)

function statusTag(status: string): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'printed') return 'success'
  if (status === 'voided') return 'danger'
  if (status === 'printing') return 'warning'
  return 'info'
}

function entryColor(eventType: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (eventType === 'voided') return 'danger'
  if (eventType === 'printed' || eventType === 'reprint') return 'success'
  if (eventType === 'print_failed' || eventType === 'timeout_reverted') return 'warning'
  if (eventType === 'allocated' || eventType === 'reclaimed') return 'primary'
  return 'info'
}

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

async function search(): Promise<void> {
  const value = codeValue.value.trim()
  if (!value) return

  loading.value = true
  error.value = null
  detail.value = null
  try {
    detail.value = await fetchCodeDetail(value)
  } catch (e) {
    error.value = e instanceof ApiError ? e.body.message : '查询失败'
  } finally {
    loading.value = false
    searched.value = true
  }
}
</script>

<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.toolbar {
  display: flex;
  gap: 12px;
  margin: 12px 0;
}
.summary {
  margin-bottom: 20px;
}
.timeline {
  padding-left: 4px;
}
.entry {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.entry-label {
  font-weight: 600;
}
.transition {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
