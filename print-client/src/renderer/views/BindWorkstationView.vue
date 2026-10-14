<template>
  <div class="bind">
    <h1>工位软件 · 首次配置</h1>
    <p class="hint">
      本机将代表所选工位。绑定后，本机产生的全部打印记录都会记到该工位上，无需每次选择。
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
      <el-form label-width="90px" class="form">
        <el-form-item label="账号">
          <el-input v-model="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" show-password />
        </el-form-item>
        <el-form-item>
          <el-button :loading="loggingIn" @click="doLogin">登录</el-button>
        </el-form-item>
      </el-form>

      <el-form v-if="me" label-width="90px" class="form">
        <el-form-item label="选择工位">
          <el-select v-model="selectedId" placeholder="请选择本机代表的工位">
            <el-option
              v-for="ws in me.workstations"
              :key="ws.id"
              :label="ws.name"
              :value="ws.id"
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
        v-if="me && me.workstations.length === 0"
        description="当前账号尚未被绑定到任何工位，请联系管理员在管理后台配置"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { ApiError, getBoundWorkstationId, setToken } from '../api/client'

const emit = defineEmits<{ bound: [workstationId: number] }>()
import {
  bindWorkstation,
  fetchMe,
  login,
  type BindResponse,
  type MeUser,
} from '../api/workstation'

const username = ref('')
const password = ref('')
const me = ref<MeUser | null>(null)
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
  } catch (e) {
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
    emit('bound', bound.value.workstation_id)
  } catch (e) {
    fail(e, '绑定工位失败')
  }
}

onMounted(async () => {
  // 已绑定过的机器直接展示结果，无需重复配置（FR-069）
  const existing = getBoundWorkstationId()
  if (existing === null) return
  try {
    const profile = await fetchMe()
    me.value = profile
    const match = profile.workstations.find((w) => w.id === existing)
    if (match) {
      bound.value = {
        workstation_id: match.id,
        name: match.name,
        company_id: profile.company_id ?? 0,
        printer_name: null,
      }
      emit('bound', match.id)
    }
  } catch {
    // 未登录时不打扰用户，走正常的首次配置流程
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
