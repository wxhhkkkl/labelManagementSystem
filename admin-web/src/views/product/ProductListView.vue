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
      <el-table-column label="默认模板" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ templateName(row.default_template_id) }}</template>
      </el-table-column>
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
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button
            v-if="me?.role === 'hq_admin'"
            size="small"
            type="primary"
            link
            @click="openBind(row)"
            >绑定模板</el-button
          >
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

    <el-dialog
      v-model="bindVisible"
      title="绑定打印模板"
      width="480px"
      :close-on-click-modal="!binding"
      :close-on-press-escape="!binding"
      :show-close="!binding"
    >
      <el-form label-width="90px">
        <el-form-item label="产品">{{ bindingProduct?.name }}</el-form-item>
        <el-form-item label="默认模板">
          <el-select
            v-model="bindingTemplateId"
            placeholder="选择打印模板"
            style="width: 100%"
            :disabled="binding"
          >
            <el-option
              v-for="item in bindableTemplates"
              :key="item.id"
              :label="`${item.name}（版本 ${item.current_version_no}）`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <p class="binding-note">新建分配单使用所选模板的当前版本，已有分配单继续使用原版本。</p>
      <el-alert
        v-if="!bindableTemplates.length"
        title="暂无可用模板，请先在模板管理中新建并启用模板。"
        type="info"
        :closable="false"
      />
      <template #footer>
        <el-button :disabled="binding" @click="bindVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="binding"
          :disabled="!bindableTemplates.some((item) => item.id === bindingTemplateId)"
          @click="saveBinding"
          >保存绑定</el-button
        >
      </template>
    </el-dialog>

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
import { computed, onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import { fetchMe, type MeUser } from '../../api/auth'
import { listTemplates, type TemplateItem } from '../../api/template'
import {
  createProduct,
  disableProduct,
  listProducts,
  updateProduct,
  type Product,
} from '../../api/product'

const rows = ref<Product[]>([])
const me = ref<MeUser | null>(null)
const templates = ref<TemplateItem[]>([])
const bindableTemplates = computed(() =>
  templates.value.filter((item) => item.status === 'active' && item.current_version_no !== null),
)
const bindVisible = ref(false)
const binding = ref(false)
const bindingProduct = ref<Product | null>(null)
const bindingTemplateId = ref<number | null>(null)

function templateName(id: number | null): string {
  if (id === null) return '未绑定'
  return templates.value.find((item) => item.id === id)?.name ?? `模板 #${id}`
}

async function openBind(product: Product): Promise<void> {
  try {
    templates.value = await listTemplates()
    bindingProduct.value = product
    bindingTemplateId.value =
      product.default_template_id ??
      (bindableTemplates.value.length === 1 ? bindableTemplates.value[0].id : null)
    bindVisible.value = true
  } catch (e) {
    fail(e, '加载模板失败')
  }
}

async function saveBinding(): Promise<void> {
  if (binding.value || !bindingProduct.value || !bindingTemplateId.value) return
  binding.value = true
  try {
    await updateProduct(bindingProduct.value.id, { default_template_id: bindingTemplateId.value })
    bindVisible.value = false
    ElMessage.success('模板已绑定')
    await load()
  } catch (e) {
    fail(e, '绑定模板失败')
  } finally {
    binding.value = false
  }
}
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
    templates.value = await listTemplates()
    me.value = await fetchMe()
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
.binding-note {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.toolbar {
  display: flex;
  gap: 12px;
  margin: 12px 0;
}
</style>
