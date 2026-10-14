<template>
  <div>
    <h2>产品管理</h2>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="按名称或编码搜索"
        clearable
        style="width: 260px"
        @keyup.enter="load"
      />
      <el-button @click="load">搜索</el-button>
      <el-button type="primary" @click="openCreate">新建产品</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="code" label="产品编码" width="140" />
      <el-table-column prop="name" label="产品名称" />
      <el-table-column prop="spec" label="规格" width="120">
        <template #default="{ row }">{{ row.spec ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="累计导入" width="100">
        <template #default="{ row }">{{ row.stats.imported }}</template>
      </el-table-column>
      <el-table-column label="已分配" width="100">
        <template #default="{ row }">{{ row.stats.allocated }}</template>
      </el-table-column>
      <el-table-column label="已打印" width="100">
        <template #default="{ row }">{{ row.stats.printed }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
            {{ row.status === 'active' ? '启用' : '停用' }}
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
            @click="disable(row)"
          >
            停用
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新建产品" width="460px">
      <el-form label-width="90px">
        <el-form-item label="产品编码">
          <el-input v-model="form.code" />
        </el-form-item>
        <el-form-item label="产品名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="规格">
          <el-input v-model="form.spec" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!form.code || !form.name" @click="submit">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import {
  createProduct,
  disableProduct,
  listProducts,
  type Product,
} from '../../api/product'

const rows = ref<Product[]>([])
const keyword = ref('')
const loading = ref(false)
const error = ref<string | null>(null)

const dialogVisible = ref(false)
const form = ref({ code: '', name: '', spec: '' })

function fail(e: unknown, fallback: string): void {
  error.value = e instanceof ApiError ? e.body.message : fallback
  ElMessage.error(error.value)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    rows.value = await listProducts(keyword.value || undefined)
  } catch (e) {
    fail(e, '加载产品失败')
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  form.value = { code: '', name: '', spec: '' }
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  try {
    await createProduct({ ...form.value })
    dialogVisible.value = false
    await load()
  } catch (e) {
    fail(e, '创建产品失败')
  }
}

async function disable(row: Product): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `停用后该产品不可再绑定新码或被分配。确认停用「${row.name}」？`,
      '停用产品',
      { type: 'warning' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await disableProduct(row.id)
    ElMessage.success('已停用')
    await load()
  } catch (e) {
    // 有在途码时服务端返回 409，把原因原样告诉用户（FR-010）
    fail(e, '停用产品失败')
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin: 12px 0;
}
</style>
