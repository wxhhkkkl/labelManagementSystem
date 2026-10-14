<template>
  <div>
    <h2>码分配与回收</h2>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <el-card shadow="never" class="section">
      <template #header><span>新建分配</span></template>

      <el-form label-width="110px">
        <el-form-item label="目标公司" :error="errors.company_id">
          <el-select v-model="form.company_id" placeholder="选择公司" @change="refreshAvailable">
            <el-option v-for="c in companies" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="产品" :error="errors.product_id">
          <el-select v-model="form.product_id" placeholder="选择产品" @change="refreshAvailable">
            <el-option
              v-for="p in activeProducts"
              :key="p.id"
              :label="`${p.name}（${p.code}）`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="分配数量" :error="errors.quantity">
          <el-input-number v-model="form.quantity" :min="1" :step="100" />
          <span v-if="available !== null" class="available">
            当前可用 <strong>{{ available }}</strong>
          </span>
        </el-form-item>

        <el-form-item label="码段范围" :error="rangeError ?? undefined">
          <el-input v-model="form.code_range_from" placeholder="起（可空）" style="width: 180px" />
          <span class="dash">~</span>
          <el-input v-model="form.code_range_to" placeholder="止（可空）" style="width: 180px" />
          <span class="hint">留空则按导入批次先进先出取码</span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submit">确认分配</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header><span>分配单</span></template>
      <el-table v-loading="loading" :data="orders" border size="small">
        <el-table-column prop="order_no" label="单号" width="230" />
        <el-table-column prop="company_name" label="公司" width="150" />
        <el-table-column prop="product_name" label="产品" />
        <el-table-column prop="code_count" label="数量" width="90" />
        <el-table-column label="码段" width="200">
          <template #default="{ row }">
            {{ row.code_range_from }} ~ {{ row.code_range_to }}
          </template>
        </el-table-column>
        <el-table-column label="模板版本" width="100">
          <template #default="{ row }">#{{ row.template_version_id }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? '有效' : '已回收' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'active'"
              size="small"
              type="danger"
              link
              @click="reclaim(row)"
            >
              回收
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import {
  createAllocation,
  listAllocations,
  reclaimAllocation,
  listCodes,
  type AllocationOrder,
} from '../../api/allocation'
import { listCompanies, type Company } from '../../api/org'
import { listProducts, type Product } from '../../api/product'
import {
  confirmText,
  isValid,
  validateAllocation,
  validateCodeRange,
  type AllocationForm,
  type Errors,
} from '../../utils/allocation'

const companies = ref<Company[]>([])
const products = ref<Product[]>([])
const orders = ref<AllocationOrder[]>([])
const available = ref<number | null>(null)

const loading = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)
const errors = ref<Errors>({})
const rangeError = ref<string | null>(null)

const form = ref<AllocationForm>({
  company_id: null,
  product_id: null,
  quantity: 100,
  code_range_from: '',
  code_range_to: '',
})

const activeProducts = computed(() => products.value.filter((p) => p.status === 'active'))

function fail(e: unknown, fallback: string): void {
  error.value = e instanceof ApiError ? e.body.message : fallback
  ElMessage.error(error.value)
}

async function load(): Promise<void> {
  loading.value = true
  try {
    orders.value = await listAllocations()
  } catch (e) {
    fail(e, '加载分配单失败')
  } finally {
    loading.value = false
  }
}

/** 查当前可分配量，给用户一个提前提示（权威判定仍在服务端）。 */
async function refreshAvailable(): Promise<void> {
  if (form.value.product_id === null) {
    available.value = null
    return
  }
  try {
    const page = await listCodes({
      product_id: form.value.product_id,
      status: 'unallocated',
      batch_id: form.value.batch_id ?? undefined,
      page_size: 1,
    })
    available.value = page.total
  } catch {
    available.value = null
  }
}

async function submit(): Promise<void> {
  errors.value = validateAllocation(form.value, available.value)
  rangeError.value = validateCodeRange(form.value.code_range_from, form.value.code_range_to)
  if (rangeError.value) errors.value.code_range = rangeError.value
  if (!isValid(errors.value)) return

  const company = companies.value.find((c) => c.id === form.value.company_id)
  const product = products.value.find((p) => p.id === form.value.product_id)
  try {
    await ElMessageBox.confirm(
      confirmText(form.value, company?.name ?? '', product?.name ?? ''),
      '确认分配',
      { type: 'warning' },
    )
  } catch {
    return
  }

  submitting.value = true
  try {
    const created = await createAllocation({
      company_id: form.value.company_id,
      product_id: form.value.product_id,
      quantity: form.value.quantity,
      batch_id: form.value.batch_id ?? null,
      code_range_from: form.value.code_range_from || null,
      code_range_to: form.value.code_range_to || null,
    })
    ElMessage.success(`已分配 ${created.allocated} 个码，单号 ${created.order.order_no}`)
    await load()
    await refreshAvailable()
  } catch (e) {
    fail(e, '分配失败')
  } finally {
    submitting.value = false
  }
}

async function reclaim(order: AllocationOrder): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认回收分配单 ${order.order_no} 中未打印的码？`, '回收', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await reclaimAllocation(order.id)
    ElMessage.success('已回收')
    await load()
    await refreshAvailable()
  } catch (e) {
    // 有已打印的码时服务端拒绝整单回收（FR-030），把原因原样展示
    fail(e, '回收失败')
  }
}

onMounted(async () => {
  try {
    companies.value = await listCompanies()
    products.value = await listProducts()
  } catch (e) {
    fail(e, '加载公司或产品失败')
  }
  await load()
})
</script>

<style scoped>
.section {
  margin-bottom: 16px;
}
.available {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.dash {
  margin: 0 8px;
}
.hint {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
