<template>
  <div>
    <h2>组织树</h2>
    <p class="hint">按公司查看组织与工位，展开公司可查看所属工位。</p>
    <div class="toolbar">
      <el-button v-if="me?.role === 'hq_admin'" type="primary" :icon="Plus" @click="openCreate">新增公司</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <el-tree
      v-if="loading || tree.length"
      v-loading="loading"
      :data="tree"
      node-key="key"
      :props="{ label: 'label', children: 'children' }"
      default-expand-all
      class="tree"
    />

    <el-empty v-if="!loading && !tree.length" description="尚未建立任何公司" />
    <el-dialog v-model="dialogVisible" title="新增公司" width="min(520px, calc(100vw - 32px))" :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving">
      <el-alert v-if="submitError" :title="submitError" type="error" show-icon :closable="false" />
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="公司编码" required :error="errors.code"><el-input v-model="form.code" maxlength="32" placeholder="请输入唯一公司编码" :disabled="saving" /></el-form-item>
        <el-form-item label="公司名称" required :error="errors.name"><el-input v-model="form.name" maxlength="128" placeholder="请输入公司名称" :disabled="saving" /></el-form-item>
        <el-form-item label="联系人"><el-input v-model="form.contact" maxlength="64" placeholder="选填" :disabled="saving" /></el-form-item>
        <el-form-item label="地区"><el-input v-model="form.region" maxlength="64" placeholder="选填" :disabled="saving" /></el-form-item>
      </el-form>
      <template #footer><el-button :disabled="saving" @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="submit">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

import { ApiError } from '../../api/client'
import { createCompany, getOrgTree, type OrgTreeNode } from '../../api/org'
import { fetchMe, type MeUser } from '../../api/auth'
import { validateCompany, isValid, type CompanyForm, type Errors } from '../../utils/validate'

const nodes = ref<OrgTreeNode[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const me = ref<MeUser | null>(null)
const dialogVisible = ref(false)
const saving = ref(false)
const submitError = ref<string | null>(null)
const errors = ref<Errors>({})
const form = ref<CompanyForm>({ code: '', name: '', contact: '', region: '' })

function openCreate() {
  form.value = { code: '', name: '', contact: '', region: '' }
  errors.value = {}
  submitError.value = null
  dialogVisible.value = true
}

async function submit() {
  if (saving.value || me.value?.role !== 'hq_admin') return
  submitError.value = null
  const values = {
    code: form.value.code.trim(), name: form.value.name.trim(),
    contact: form.value.contact?.trim() || null, region: form.value.region?.trim() || null,
  }
  errors.value = validateCompany({ code: values.code, name: values.name })
  if (!isValid(errors.value)) return
  saving.value = true
  try {
    await createCompany(values)
    dialogVisible.value = false
    ElMessage.success('公司创建成功')
    await load()
  } catch (e) {
    submitError.value = e instanceof ApiError ? e.body.message : '创建公司失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

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

async function load() {
  loading.value = true
  error.value = null
  try {
    nodes.value = await getOrgTree()
  } catch (e) {
    error.value = e instanceof ApiError ? e.body.message : '加载组织树失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    load(),
    fetchMe().then(value => { me.value = value }).catch(() => { /* 未确认身份时不展示新增入口 */ }),
  ])
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
