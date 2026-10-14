<template>
  <div>
    <h2>码池查询</h2>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="toolbar">
      <el-select v-model="filters.product_id" placeholder="产品" clearable @change="reload">
        <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态" clearable @change="reload">
        <el-option
          v-for="s in STATUSES"
          :key="s.value"
          :label="s.label"
          :value="s.value"
        />
      </el-select>
    </div>

    <el-table v-loading="loading" :data="page.items" border size="small">
      <el-table-column prop="code_value" label="码值" width="220" />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="product_id" label="产品 ID" width="100" />
      <el-table-column label="归属公司" width="120">
        <template #default="{ row }">{{ row.company_id ?? '总部码池' }}</template>
      </el-table-column>
      <el-table-column prop="print_count" label="打印次数" width="100" />
      <el-table-column prop="reprint_count" label="补打次数" width="100" />
    </el-table>

    <el-pagination
      class="pager"
      layout="total, prev, pager, next"
      :total="page.total"
      :current-page="page.page"
      :page-size="page.page_size"
      @current-change="onPage"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import { listCodes, type CodePage } from '../../api/allocation'
import { listProducts, type Product } from '../../api/product'

const STATUSES = [
  { value: 'unallocated', label: '待分配' },
  { value: 'allocated', label: '已分配' },
  { value: 'printing', label: '打印中' },
  { value: 'printed', label: '已打印' },
  { value: 'voided', label: '已作废' },
]

const STATUS_LABELS: Record<string, string> = Object.fromEntries(
  STATUSES.map((s) => [s.value, s.label]),
)

const products = ref<Product[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const filters = ref<{ product_id?: number; status?: string }>({})
const page = ref<CodePage>({ items: [], total: 0, page: 1, page_size: 20 })

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

function statusTag(status: string): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'printed') return 'success'
  if (status === 'voided') return 'danger'
  if (status === 'printing') return 'warning'
  return 'info'
}

async function load(targetPage = 1): Promise<void> {
  loading.value = true
  error.value = null
  try {
    page.value = await listCodes({
      product_id: filters.value.product_id,
      status: filters.value.status,
      page: targetPage,
      page_size: 20,
    })
  } catch (e) {
    error.value = e instanceof ApiError ? e.body.message : '加载码池失败'
  } finally {
    loading.value = false
  }
}

function reload(): void {
  void load(1)
}

function onPage(next: number): void {
  void load(next)
}

onMounted(async () => {
  try {
    products.value = await listProducts()
  } catch {
    // 产品列表拉不到不影响查码池
  }
  await load()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin: 12px 0;
}
.pager {
  margin-top: 12px;
}
</style>
