<template>
  <div>
    <h2>打印明细</h2>
    <p class="hint">
      按公司 / 工位 / 操作员 / 产品 / 时间段筛选。子公司只能看到本公司的记录。
    </p>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="toolbar">
      <el-select v-model="filters.product_id" placeholder="产品" clearable @change="load">
        <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>

      <el-select v-model="filters.workstation_id" placeholder="工位" clearable @change="load">
        <el-option v-for="w in workstations" :key="w.id" :label="w.name" :value="w.id" />
      </el-select>

      <el-date-picker
        v-model="range"
        type="datetimerange"
        range-separator="至"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        value-format="YYYY-MM-DDTHH:mm:ss"
        @change="load"
      />

      <el-button @click="load">查询</el-button>
      <el-button type="primary" :loading="exporting" @click="onExport">导出 Excel</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border size="small">
      <el-table-column prop="code_value" label="码值" width="200" />
      <el-table-column prop="product_name" label="产品" />
      <el-table-column prop="company_name" label="公司" width="140" />
      <el-table-column prop="workstation_name" label="工位" width="140" />
      <el-table-column prop="operator_name" label="操作员" width="110" />
      <el-table-column prop="printer_name" label="打印机" width="150" />
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-tag :type="row.print_type === 'reprint' ? 'warning' : 'info'" size="small">
            {{ row.print_type === 'reprint' ? '补打' : '首次' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="结果" width="110">
        <template #default="{ row }">
          <el-tag :type="resultTag(row.result)" size="small">{{ resultLabel(row.result) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="failure_reason" label="失败原因" width="150">
        <template #default="{ row }">{{ row.failure_reason ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="打印时间" width="180">
        <template #default="{ row }">{{ formatTime(row.printed_at) }}</template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !rows.length" description="所选条件下没有打印记录" />
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import { listWorkstations, type Workstation } from '../../api/org'
import { listProducts, type Product } from '../../api/product'
import {
  exportPrintDetails,
  fetchPrintDetails,
  type PrintDetail,
  type PrintDetailParams,
} from '../../api/report'

const rows = ref<PrintDetail[]>([])
const products = ref<Product[]>([])
const workstations = ref<Workstation[]>([])
const range = ref<[string, string] | null>(null)
const filters = ref<PrintDetailParams>({})
const loading = ref(false)
const exporting = ref(false)
const error = ref<string | null>(null)

function resultTag(result: string): 'success' | 'danger' | 'warning' {
  if (result === 'succeeded') return 'success'
  if (result === 'failed') return 'danger'
  return 'warning'
}

function resultLabel(result: string): string {
  return (
    {
      succeeded: '成功',
      failed: '失败',
      timeout_reverted: '超时回退',
    }[result] ?? result
  )
}

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

/** 把界面上的筛选条件整理成接口参数。 */
function params(): PrintDetailParams {
  return {
    product_id: filters.value.product_id,
    workstation_id: filters.value.workstation_id,
    printed_from: range.value?.[0],
    printed_to: range.value?.[1],
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    rows.value = await fetchPrintDetails(params())
  } catch (e) {
    error.value = e instanceof ApiError ? e.body.message : '加载打印明细失败'
  } finally {
    loading.value = false
  }
}

async function onExport(): Promise<void> {
  exporting.value = true
  try {
    await exportPrintDetails(params())
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.body.message : '导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  try {
    products.value = await listProducts()
  } catch {
    // 产品列表拿不到不影响查明细
  }
  try {
    workstations.value = await listWorkstations()
  } catch {
    // 子公司可能没有工位列表权限，忽略
  }
  await load()
})
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
</style>
