<template>
  <div class="bind">
    <h1>{{ me ? '绑定本机工位' : '操作员登录' }}</h1>
    <p class="hint">
      每次打开软件请操作员登录。已绑定的电脑登录后自动进入原工位，首次使用需选择本企业的可用工位。
    </p>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <el-alert
      v-if="bound"
      type="success"
      show-icon
      :closable="false"
      :title="`已绑定工位：${bound.name}`"
      :description="`公司 ID：${bound.company_id} · 默认打印机：${bound.printer_name ?? '尚未设置'}`"
    />

    <template v-if="!bound">
      <el-form v-if="!me" label-width="90px" class="form" @submit.prevent="doLogin">
        <el-form-item label="账号">
          <el-input v-model="username" placeholder="请输入工位操作员账号" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" show-password placeholder="请输入密码" autocomplete="current-password" @keyup.enter="doLogin" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loggingIn" :disabled="!username.trim() || !password" @click="doLogin">登录</el-button>
        </el-form-item>
      </el-form>

      <el-form v-if="me" label-width="90px" class="form">
        <el-form-item label="所属企业">{{ me.company?.name ?? '未关联企业' }}</el-form-item>
        <el-form-item label="选择工位">
          <el-select v-model="selectedId" placeholder="请选择本机代表的工位">
            <el-option
              v-for="ws in availableWorkstations"
              :key="ws.workstation_id"
              :label="ws.name"
              :value="ws.workstation_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :disabled="selectedId === null" @click="doBind">
            绑定本机工位
          </el-button>
        </el-form-item>
      </el-form>

      <el-empty
        v-if="me && availableWorkstations.length === 0"
        description="所属企业暂无未绑定的可用工位，请在管理后台新增工位或检查现有机器绑定"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { ApiError, setBoundWorkstationId, setBoundPrinter, setToken } from '../api/client'

const emit = defineEmits<{ bound: [workstationId: number, user: MeUser, station: BindResponse] }>()
import {
  bindWorkstation,
  login,
  listAvailableWorkstations,
  getMachineBinding,
  type BindResponse,
  type MeUser,
} from '../api/workstation'
const props = defineProps<{ sessionUser?: MeUser | null }>()

const username = ref('')
const password = ref('')
const me = ref<MeUser | null>(null)
const availableWorkstations = ref<BindResponse[]>([])
const selectedId = ref<number | null>(null)
const bound = ref<BindResponse | null>(null)
const error = ref<string | null>(null)
const loggingIn = ref(false)

function fail(e: unknown, fallback: string): void {
  error.value = e instanceof ApiError ? e.body.message : fallback
}

async function doLogin(): Promise<void> {
  error.value = null
  loggingIn.value = true
  try {
    const result = await login(username.value, password.value)
    setToken(result.access_token)
    me.value = result.user
    password.value = ''
    await loadBinding()
  } catch (e) {
    me.value = null
    setToken(null)
    fail(e, '登录失败')
  } finally {
    loggingIn.value = false
  }
}

async function doBind(): Promise<void> {
  if (selectedId.value === null) return
  error.value = null
  try {
    bound.value = await bindWorkstation(selectedId.value)
    if (me.value) emit('bound', bound.value.workstation_id, me.value, bound.value)
  } catch (e) {
    fail(e, '绑定工位失败')
    availableWorkstations.value = await listAvailableWorkstations().catch(() => [])
    selectedId.value = null
  }
}

async function loadBinding(): Promise<void> {
  const current = await getMachineBinding()
  if (current) {
    setBoundWorkstationId(current.workstation_id)
    setBoundPrinter(current.printer_name)
    if (me.value) emit('bound', current.workstation_id, me.value, current)
    return
  }
  setBoundWorkstationId(null)
  availableWorkstations.value = await listAvailableWorkstations()
  selectedId.value = availableWorkstations.value.length === 1 ? availableWorkstations.value[0].workstation_id : null
}

onMounted(async () => {
  if (!props.sessionUser) return
  try {
    me.value = props.sessionUser
    await loadBinding()
  } catch (e) {
    me.value = null
    fail(e, '识别本机工位失败，请重新登录')
  }
})
</script>

<style scoped>
.bind {
  max-width: 560px;
  margin: 48px auto;
}
.hint {
  color: #666;
  font-size: 13px;
}
.form {
  margin-top: 16px;
}
</style>
