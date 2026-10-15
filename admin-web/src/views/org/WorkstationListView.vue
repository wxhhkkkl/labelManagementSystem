<template>
  <div>
    <h2>工位管理</h2>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="toolbar">
      <el-select
        v-if="me?.role === 'hq_admin'"
        v-model="companyFilter"
        placeholder="按公司筛选"
        clearable
        @change="load"
      >
        <el-option v-for="c in companies" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-button type="primary" @click="dialogVisible = true">新建工位</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="code" label="工位编码" width="140" />
      <el-table-column prop="name" label="工位名称" />
      <el-table-column prop="company_name" label="所属公司" width="180" />
      <el-table-column label="机器绑定" width="110">
        <template #default="{ row }"
          ><el-tag :type="row.machine_bound ? 'success' : 'info'">{{
            row.machine_bound ? '已绑定' : '未绑定'
          }}</el-tag></template
        >
      </el-table-column>
      <el-table-column prop="printer_name" label="绑定打印机" width="180">
        <template #default="{ row }">{{ row.printer_name ?? '未绑定' }}</template>
      </el-table-column>
      <el-table-column label="在线" width="90">
        <template #default="{ row }">
          <el-tag :type="row.online ? 'success' : 'info'" size="small">
            {{ row.online ? '在线' : '离线' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'danger'" size="small">
            {{ row.status === 'active' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button
            v-if="row.machine_bound"
            size="small"
            type="warning"
            link
            :loading="unbindingId === row.id"
            @click="unbind(row)"
            >解绑机器</el-button
          >
          <el-button
            v-if="row.status === 'active'"
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

    <el-dialog v-model="dialogVisible" title="新建工位" width="480px">
      <el-form label-width="90px">
        <el-form-item label="工位编码" :error="errors.code">
          <el-input v-model="form.code" />
        </el-form-item>
        <el-form-item label="工位名称" :error="errors.name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="所属公司" :error="errors.company_id">
          <el-select v-model="form.company_id" :disabled="me?.role === 'sub_admin'">
            <el-option v-for="c in companies" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="打印机">
          <el-input v-model="form.printer_name" placeholder="可稍后由工位端绑定" />
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import { fetchMe, type MeUser } from '../../api/auth'
import {
  createWorkstation,
  disableWorkstation,
  listCompanies,
  listWorkstations,
  unbindWorkstation,
  type Company,
  type Workstation,
} from '../../api/org'
import { isValid, validateWorkstation, type Errors } from '../../utils/validate'

const rows = ref<Workstation[]>([])
const me = ref<MeUser | null>(null)
const unbindingId = ref<number | null>(null)

async function unbind(row: Workstation): Promise<void> {
  if (unbindingId.value !== null) return
  try {
    await ElMessageBox.confirm(
      `确认解绑「${row.name}」的机器？原机器将返回绑定页面，打印机配置会清除。`,
      '解绑工位机器',
      { type: 'warning', confirmButtonText: '确认解绑' },
    )
  } catch {
    return
  }
  unbindingId.value = row.id
  try {
    await unbindWorkstation(row.id)
    ElMessage.success('工位机器已解绑')
    await load()
  } catch (e) {
    fail(e, '解绑工位失败')
  } finally {
    unbindingId.value = null
  }
}
const companies = ref<Company[]>([])
const companyFilter = ref<number | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const dialogVisible = ref(false)
const errors = ref<Errors>({})
const form = ref({ code: '', name: '', company_id: null as number | null, printer_name: '' })

function fail(e: unknown, fallback: string): void {
  error.value = e instanceof ApiError ? e.body.message : fallback
  ElMessage.error(error.value)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    rows.value = await listWorkstations(companyFilter.value ?? undefined)
  } catch (e) {
    fail(e, '加载工位失败')
  } finally {
    loading.value = false
  }
}

async function submit(): Promise<void> {
  errors.value = validateWorkstation(form.value)
  if (!isValid(errors.value)) return
  try {
    await createWorkstation({ ...form.value })
    dialogVisible.value = false
    form.value = {
      code: '',
      name: '',
      company_id: me.value?.role === 'sub_admin' ? me.value.company_id : null,
      printer_name: '',
    }
    await load()
  } catch (e) {
    fail(e, '创建工位失败')
  }
}

async function disable(id: number): Promise<void> {
  try {
    await disableWorkstation(id)
    await load()
  } catch (e) {
    fail(e, '停用工位失败')
  }
}

onMounted(async () => {
  try {
    me.value = await fetchMe()
    if (me.value.role === 'sub_admin') {
      const company = me.value.company
      companies.value = company
        ? [{ ...company, code: '', contact: null, region: null, status: 'active' }]
        : []
      form.value.company_id = me.value.company_id
    } else {
      companies.value = await listCompanies()
    }
  } catch (e) {
    fail(e, '加载公司列表失败')
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
</style>
