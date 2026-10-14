<template>
  <section class="settings">
    <h3>工位设置</h3>

    <el-alert
      :title="status.message"
      :type="status.state === 'ok' ? 'success' : 'warning'"
      show-icon
      :closable="false"
    />

    <el-form label-width="110px" class="form">
      <el-form-item label="本机打印机">
        <el-select v-model="selected" placeholder="选择本机打印机" style="width: 320px">
          <el-option
            v-for="printer in printers"
            :key="printer.name"
            :label="printerLabel(printer)"
            :value="printer.name"
          />
        </el-select>
        <el-button type="primary" :disabled="!selected" :loading="saving" @click="save">
          保存
        </el-button>
      </el-form-item>

      <el-form-item label="打印机清单">
        <el-button size="small" @click="refresh">重新读取</el-button>
        <span class="hint">
          清单来自本机操作系统，不是服务端——换个型号只要装好驱动就能选到。
        </span>
      </el-form-item>
    </el-form>

    <el-alert
      v-if="needsRebind"
      type="warning"
      show-icon
      :closable="false"
      title="原先绑定的打印机已不在本机清单中"
      description="可能是换了电脑或重装了驱动。请重新选择一台打印机并保存。"
    />

    <p class="hint">
      已保存：{{ boundPrinter ?? '未绑定' }}
      <template v-if="recoveries > 0"> · 打印服务已自动重连 {{ recoveries }} 次</template>
    </p>
  </section>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

import { ApiError, getBoundPrinter, setBoundPrinter } from '../api/client'
import { setWorkstationPrinter } from '../api/workstation'
import { printerLabel, normalizePrinters, type PrinterInfo } from '../../print-service/printers'
import { usePrintServiceStatus } from '../composables/usePrintServiceStatus'

const props = defineProps<{ workstationId: number }>()

const { status, needsRebind, recoveries, start } = usePrintServiceStatus()
const printers = ref<PrinterInfo[]>([])
const boundPrinter = ref<string | null>(getBoundPrinter())
const selected = ref<string | null>(boundPrinter.value)
const saving = ref(false)

async function refresh(): Promise<void> {
  // 清单要走打印服务拿（它才有 OS 枚举能力），拿不到就报服务未启动
  const { listPrinters } = await import('../api/print-service')
  try {
    const names = await listPrinters()
    printers.value = normalizePrinters(names.map((name) => ({ name })))
  } catch {
    printers.value = []
  }
}

async function save(): Promise<void> {
  if (!selected.value) return
  saving.value = true
  try {
    // 两端都记：本机记名字（打印时要传给打印服务），服务端记工位的绑定打印机
    setBoundPrinter(selected.value)
    boundPrinter.value = selected.value
    await setWorkstationPrinter(props.workstationId, selected.value)
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.body.message : '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  start()
  await refresh()
})
</script>

<style scoped>
.settings {
  max-width: 720px;
}
.form {
  margin-top: 16px;
}
.hint {
  margin-left: 12px;
  font-size: 12px;
  color: #888;
}
</style>
