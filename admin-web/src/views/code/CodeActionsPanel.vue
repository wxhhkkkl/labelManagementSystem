<template>
  <div class="panel">
    <h3>{{ me?.role === 'hq_admin' ? '补打与作废' : '码补打' }}</h3>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert
      v-if="notice"
      :title="notice"
      type="success"
      show-icon
      :closable="false"
      class="notice"
    />

    <el-form label-width="90px" class="form">
      <el-form-item label="码值" :error="reasonErrors.codeValue">
        <el-input v-model="codeValue" placeholder="输入或扫码定位单个码" style="width: 320px" />
      </el-form-item>

      <el-form-item label="原因" :error="reasonErrors.reason">
        <el-input v-model="reason" style="width: 420px" />
        <div class="presets">
          <el-tag
            v-for="preset in REASON_PRESETS"
            :key="preset"
            size="small"
            class="preset"
            @click="reason = preset"
          >
            {{ preset }}
          </el-tag>
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="busy" @click="doReprint">补打</el-button>
        <el-button v-if="me?.role === 'hq_admin'" type="danger" :loading="busy" @click="doVoid"
          >作废</el-button
        >
      </el-form-item>
    </el-form>

    <p class="hint">
      补打会派发到该码**最近一次打印的原工位**并自动出纸，无需选择打印机；
      原工位离线时会被拒绝。<template v-if="me?.role === 'hq_admin'"
        >作废是不可恢复的终态。</template
      >
    </p>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { fetchMe, type MeUser } from '../../api/auth'

import { ApiError } from '../../api/client'
import { requestReprint, voidCodes } from '../../api/reprint'
import {
  REASON_PRESETS,
  explainError,
  isValid,
  validateReason,
  validateReprint,
  validateVoid,
  voidConfirmText,
  type Errors,
} from '../../utils/reprint'

const emit = defineEmits<{ done: [] }>()

const codeValue = ref('')
const me = ref<MeUser | null>(null)
onMounted(async () => {
  me.value = await fetchMe()
})
const reason = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const reasonErrors = ref<Errors>({})

function fail(e: unknown, fallback: string): void {
  error.value = e instanceof ApiError ? explainError(e.body.error_code, e.body.message) : fallback
  ElMessage.error(error.value)
}

async function doReprint(): Promise<void> {
  reasonErrors.value = validateReprint({ codeValue: codeValue.value || null, reason: reason.value })
  if (!isValid(reasonErrors.value)) return

  error.value = null
  notice.value = null
  busy.value = true
  try {
    const task = await requestReprint(codeValue.value.trim(), reason.value)
    notice.value = `补打任务已派发到工位「${task.target_workstation_name ?? task.target_workstation_id}」，稍后自动出纸`
    ElMessage.success('补打任务已创建')
    reason.value = ''
    emit('done')
  } catch (e) {
    fail(e, '补打失败')
  } finally {
    busy.value = false
  }
}

async function doVoid(): Promise<void> {
  const values = codeValue.value
    .split(/[\s,，]+/)
    .map((v) => v.trim())
    .filter(Boolean)

  reasonErrors.value = validateVoid({ codeValues: values, reason: reason.value })
  // 单独校验原因，避免"操作员没填原因"被笼统报成"请选择码"
  if (reasonErrors.value.reason === undefined) {
    const onlyReason = validateReason(reason.value)
    if (onlyReason) reasonErrors.value.reason = onlyReason
  }
  if (!isValid(reasonErrors.value)) return

  try {
    await ElMessageBox.confirm(voidConfirmText(values.length, reason.value), '确认作废', {
      type: 'warning',
    })
  } catch {
    return
  }

  error.value = null
  notice.value = null
  busy.value = true
  try {
    const result = await voidCodes(values, reason.value)
    const skipped = result.skipped.length ? `，${result.skipped.length} 个已作废被跳过` : ''
    notice.value = `已作废 ${result.voided.length} 个码${skipped}`
    ElMessage.success('作废完成')
    reason.value = ''
    emit('done')
  } catch (e) {
    fail(e, '作废失败')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.panel {
  max-width: 720px;
}
.notice {
  margin-bottom: 12px;
}
.form {
  margin-top: 12px;
}
.presets {
  margin-top: 6px;
}
.preset {
  margin-right: 6px;
  cursor: pointer;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.8;
}
</style>
