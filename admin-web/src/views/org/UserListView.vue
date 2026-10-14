<template>
  <div>
    <h2>账号管理</h2>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="toolbar">
      <span v-if="me" class="hint">
        当前身份：{{ ROLE_LABELS[me.role] }}
        <template v-if="me.company"> · {{ me.company.name }}</template>
      </span>
      <el-button type="primary" @click="dialogVisible = true">新建账号</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="username" label="账号" width="160" />
      <el-table-column prop="display_name" label="姓名" width="160" />
      <el-table-column label="角色" width="140">
        <template #default="{ row }">{{ ROLE_LABELS[row.role as Role] ?? row.role }}</template>
      </el-table-column>
      <el-table-column prop="company_id" label="所属公司 ID" width="120">
        <template #default="{ row }">{{ row.company_id ?? '总部' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'danger'" size="small">
            {{ row.status === 'active' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'active' && row.id !== me?.id"
            size="small"
            type="danger"
            link
            @click="disable(row.id)"
          >
            停用
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新建账号" width="520px">
      <el-form label-width="90px">
        <el-form-item label="账号" :error="errors.username">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="姓名" :error="errors.display_name">
          <el-input v-model="form.display_name" />
        </el-form-item>
        <el-form-item label="密码" :error="errors.password">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="角色" :error="errors.role">
          <!-- 选项按当前身份裁剪，避免选到必然被拒的角色（FR-004） -->
          <el-select v-model="form.role">
            <el-option
              v-for="r in roleOptions"
              :key="r"
              :label="ROLE_LABELS[r]"
              :value="r"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.role !== 'hq_admin'" label="所属公司" :error="errors.company_id">
          <el-select v-model="form.company_id" :disabled="me?.role === 'sub_admin'">
            <el-option v-for="c in companies" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import { fetchMe, type MeUser } from '../../api/auth'
import {
  createUser,
  disableUser,
  listCompanies,
  listUsers,
  type Company,
  type User,
} from '../../api/org'
import {
  ROLE_LABELS,
  assignableRoles,
  isValid,
  validateUser,
  type Errors,
  type Role,
  type UserForm,
} from '../../utils/validate'

const rows = ref<User[]>([])
const companies = ref<Company[]>([])
const me = ref<MeUser | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const dialogVisible = ref(false)
const errors = ref<Errors>({})
const form = ref<UserForm>({
  username: '',
  display_name: '',
  password: '',
  role: 'operator',
  company_id: null,
})

const roleOptions = computed<Role[]>(() =>
  me.value ? assignableRoles(me.value.role) : ['operator'],
)

function fail(e: unknown, fallback: string): void {
  error.value = e instanceof ApiError ? e.body.message : fallback
  ElMessage.error(error.value)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    rows.value = await listUsers()
  } catch (e) {
    fail(e, '加载账号失败')
  } finally {
    loading.value = false
  }
}

async function submit(): Promise<void> {
  if (!me.value) return
  errors.value = validateUser(form.value, me.value.role, me.value.company_id)
  if (!isValid(errors.value)) return
  try {
    await createUser({ ...form.value })
    dialogVisible.value = false
    form.value = {
      username: '',
      display_name: '',
      password: '',
      role: 'operator',
      company_id: me.value.company_id,
    }
    await load()
  } catch (e) {
    fail(e, '创建账号失败')
  }
}

async function disable(id: number): Promise<void> {
  try {
    await disableUser(id)
    await load()
  } catch (e) {
    fail(e, '停用账号失败')
  }
}

onMounted(async () => {
  try {
    me.value = await fetchMe()
    form.value.company_id = me.value.company_id
    if (me.value.role !== 'hq_admin') form.value.role = 'operator'
  } catch (e) {
    fail(e, '获取当前用户失败')
  }
  try {
    companies.value = await listCompanies()
  } catch {
    // 子公司管理员无公司列表权限时可忽略，其公司由 me 决定
  }
  await load()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 12px 0;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
