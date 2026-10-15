<template>
  <div class="print">
    <header class="head"><div><p class="eyebrow">PRINT WORKSPACE</p><h1>工位打印</h1><p class="page-description">选择产品、查看模板并按数量打印。</p></div><div class="print-status"><span class="status" :class="serviceOk ? 'ok' : 'bad'">{{ serviceOk ? '打印服务正常' : '打印服务未启动' }}</span><span v-if="boundName" class="bound">工位：{{ boundName }}</span></div></header>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <div class="print-layout">
      <section class="print-config station-panel">
        <h2>打印配置</h2>
        <div class="config-body">
          <label class="field-label">产品</label>
          <el-select v-model="productId" placeholder="选择产品" aria-label="选择产品" @change="loadCodes"><el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" /></el-select>
          <label class="field-label">当前打印机</label>
          <p class="default-printer">{{ printerName || '请到工位状态选择打印机' }}</p>
          <div class="available-codes"><span>当前可打印码</span><strong>{{ total }} <small>个</small></strong></div>
          <label class="field-label">打印数量</label>
          <el-input-number v-model="quantity" :min="1" :max="Math.max(total, 1)" aria-label="打印数量" />
          <el-button class="start-print" type="primary" :loading="printing" :disabled="!canPrint" @click="doPrint">开始打印</el-button>
          <p class="hint">可打印码由本公司全部工位共享。打印失败后可标记并回退。</p>
        </div>
      </section>
      <section class="station-panel template-panel">
        <h2>当前模板</h2>
        <template v-if="preview">
          <p class="template-caption">{{ preview.name }} · V{{ preview.version_no }}<br>{{ preview.elements_json.paper_width_mm }} × {{ preview.elements_json.paper_height_mm }} mm</p>
          <TemplatePreview :doc="preview.elements_json" :data="preview.data" />
          <p class="preview-note">下一张待打印码的模板。日期、流水号空白处将在首次打印时生成。</p>
        </template>
        <el-empty v-else :image-size="64" description="暂无待打印模板" />
      </section>
      <div class="print-results">
        <section class="station-panel">
          <h2>本次任务</h2>
          <el-table v-if="task.length" :data="task" size="small" height="140"><el-table-column prop="code_value" label="码值" min-width="200" /><el-table-column label="结果" width="140"><template #default="{ row }"><el-tag :type="tagType(row)" size="small">{{ tagLabel(row) }}</el-tag></template></el-table-column><el-table-column label="说明" min-width="160"><template #default="{ row }">{{ row.message ?? '—' }}</template></el-table-column></el-table>
          <el-empty v-else :image-size="40" description="尚未发起打印" />
          <div v-if="hasLocked" class="failure-action"><el-button type="warning" :loading="confirming" @click="doConfirmFailed">标记失败并回退</el-button></div>
        </section>
        <TaskView v-if="workstationId" :workstation-id="workstationId" :printer-name="printerName" :service-ok="serviceOk" />
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { ApiError, getBoundWorkstationId, getBoundPrinter, setBoundPrinter, request } from '../api/client'
import { getMachineBinding, setWorkstationPrinter } from '../api/workstation'
import {
  confirmPrint,
  listPrintableCodes,
  startPrint,
  type AcceptedPrint,
  type PrintableCode,
} from '../api/print'
import { isPrintServiceAlive, getDefaultPrinter, listPrinters, print } from '../api/print-service'
import { useHeartbeat } from '../composables/useHeartbeat'
import TaskView from './TaskView.vue'
import TemplatePreview from '../components/TemplatePreview.vue'
import type { TemplateDoc } from '../../print-render/renderer'
const preview = ref<{name:string; version_no:number; elements_json:TemplateDoc; data:Record<string,string>} | null>(null)

interface TaskRow {
  code_value: string
  outcome: 'accepted' | 'rejected' | 'printed' | 'rolled_back'
  message?: string
}

const workstationId = ref<number | null>(null)
const boundName = ref<string | null>(null)
const products = ref<{ id: number; name: string }[]>([])
const productId = ref<number | null>(null)
const printerName = ref<string>('')
const quantity = ref(1)
const total = ref(0)
const codes = ref<PrintableCode[]>([])
const task = ref<TaskRow[]>([])
/** 已预占但尚未确认的码 —— 这些才是"打印中"，可以标记失败回退 */
const locked = ref<AcceptedPrint[]>([])

const printing = ref(false)
const confirming = ref(false)
const serviceOk = ref(false)
const error = ref<string | null>(null)

const canPrint = computed(
  () => !!workstationId.value && !!productId.value && !!printerName.value && serviceOk.value && total.value > 0 && !printing.value,
)
const hasLocked = computed(() => locked.value.length > 0)

function tagType(row: TaskRow): 'success' | 'danger' | 'warning' | 'info' {
  if (row.outcome === 'printed') return 'success'
  if (row.outcome === 'rejected') return 'danger'
  if (row.outcome === 'rolled_back') return 'warning'
  return 'info'
}

function tagLabel(row: TaskRow): string {
  return {
    accepted: '已出纸',
    printed: '已打印',
    rejected: '被拒绝',
    rolled_back: '已回退',
  }[row.outcome]
}

function fail(e: unknown, fallback: string): void {
  error.value = e instanceof ApiError ? e.body.message : fallback
  ElMessage.error(error.value)
}

async function refreshServiceStatus(): Promise<void> {
  serviceOk.value = await isPrintServiceAlive()
  if (serviceOk.value) {
    try {
      const saved = getBoundPrinter()
      const selected = saved ?? await getDefaultPrinter() ?? ''
      printerName.value = (await listPrinters()).includes(selected) ? selected : ''
      if (!saved && printerName.value && workstationId.value) {
        await setWorkstationPrinter(workstationId.value, selected)
        setBoundPrinter(selected)
      }
    } catch {
      printerName.value = ''
    }
  }
}

let codeRequest = 0
async function loadCodes(): Promise<void> {
  const currentRequest = ++codeRequest
  preview.value = null
  codes.value = []; total.value = 0
  if (!workstationId.value || !productId.value) return
  try {
    const page = await listPrintableCodes(workstationId.value, productId.value)
    if (currentRequest !== codeRequest) return
    codes.value = page.items
    total.value = page.total
    quantity.value = Math.min(quantity.value, Math.max(page.total, 1))
    const nextPreview = await request<typeof preview.value>(`/api/v1/workstation/template?workstation_id=${workstationId.value}&product_id=${productId.value}`)
    if(currentRequest === codeRequest) preview.value = nextPreview
  } catch (e) {
    fail(e, '加载可打印码失败')
  }
}

async function doPrint(): Promise<void> {
  if (!workstationId.value || !productId.value) return
  error.value = null
  await refreshServiceStatus()
  if (!serviceOk.value || !printerName.value) {
    ElMessage.warning('请到工位状态选择可用打印机，并确认打印服务正常')
    return
  }
  printing.value = true
  const activePrinter = printerName.value

  try {
    const selected = codes.value.slice(0, quantity.value).map((c) => c.code_value)

    // 1) 预占：服务端把码置为"打印中"并返回模板
    const response = await startPrint(workstationId.value, selected, activePrinter)

    task.value = [
      ...response.accepted.map(
        (a): TaskRow => ({ code_value: a.code_value, outcome: 'accepted' }),
      ),
      ...response.rejected.map(
        (r): TaskRow => ({ code_value: r.code_value, outcome: 'rejected', message: r.message }),
      ),
    ]
    locked.value = response.accepted

    if (!response.accepted.length) {
      ElMessage.warning('没有可打印的码')
      return
    }

    // 2) 出纸：经本地打印服务静默打印
    if (!serviceOk.value) {
      ElMessage.warning('打印服务未启动，已预占但未出纸；可标记失败回退')
      return
    }

    const results = []
    for (const item of response.accepted) {
      const outcome = await print({
        doc: item.elements_json,
        data: item.data,
        deviceName: activePrinter,
      })
      results.push(
        outcome.ok
          ? { code_value: item.code_value, outcome: 'succeeded' as const, printer_name: activePrinter }
          : {
              code_value: item.code_value,
              outcome: 'failed' as const,
              failure_reason: outcome.error ?? '打印服务报错',
            },
      )
    }

    // 3) 确认：成功置"已打印"，失败回退（不计补打）
    const confirmed = await confirmPrint(workstationId.value, results)
    // 按码值查表，不能按下标对齐——服务端的 confirmed 顺序与 results 不保证一致
    const outcomeByCode = new Map(results.map((r) => [r.code_value, r.outcome]))
    const okSet = new Set(
      confirmed.confirmed.filter((value) => outcomeByCode.get(value) === 'succeeded'),
    )
    const failedSet = new Set(
      confirmed.confirmed.filter((value) => outcomeByCode.get(value) === 'failed'),
    )

    task.value = task.value.map((row) => {
      if (okSet.has(row.code_value)) return { ...row, outcome: 'printed' as const }
      if (failedSet.has(row.code_value)) {
        return { ...row, outcome: 'rolled_back' as const, message: '打印失败，已回退' }
      }
      return row
    })
    locked.value = response.accepted.filter((a) => !confirmed.confirmed.includes(a.code_value))

    await loadCodes()
  } catch (e) {
    fail(e, '打印失败')
  } finally {
    printing.value = false
  }
}

async function doConfirmFailed(): Promise<void> {
  if (!workstationId.value || !locked.value.length) return
  confirming.value = true
  try {
    const results = locked.value.map((item) => ({
      code_value: item.code_value,
      outcome: 'failed' as const,
      failure_reason: '操作员标记打印失败',
    }))
    await confirmPrint(workstationId.value, results)
    task.value = task.value.map((row) =>
      locked.value.some((l) => l.code_value === row.code_value)
        ? { ...row, outcome: 'rolled_back' as const, message: '已标记失败，码已回退' }
        : row,
    )
    locked.value = []
    await loadCodes()
    ElMessage.success('已回退，可重新打印')
  } catch (e) {
    fail(e, '标记失败失败')
  } finally {
    confirming.value = false
  }
}

let poll: ReturnType<typeof setInterval> | null = null

// 心跳必须持续上报：服务端靠它判断本工位是否在线，
// 停发超过 30 秒后对该工位的补打就会被拒绝（FR-056）
const heartbeat = useHeartbeat(
  () => workstationId.value,
  () => serviceOk.value,
)

onMounted(async () => {
  window.addEventListener('lms:printer-changed', refreshServiceStatus)
  workstationId.value = getBoundWorkstationId()
  try {
    const currentBinding = await getMachineBinding()
    boundName.value = currentBinding?.name ?? null
    const items = await request<{ id: number; name: string; status: string }[]>('/api/v1/products/options')
    products.value = items.filter(product => product.status === 'active')
    if (productId.value === null && products.value.length === 1) {
      productId.value = products.value[0].id
      await loadCodes()
    }
  } catch (e) {
    fail(e, '加载产品失败')
  }
  await refreshServiceStatus()
  if (workstationId.value) heartbeat.start()
  // 打印服务可能稍后才起来（或中途重启），定期探测而不是只测一次
  poll = setInterval(refreshServiceStatus, 5000)
})

onUnmounted(() => {
  if (poll !== null) clearInterval(poll)
  heartbeat.stop()
  window.removeEventListener('lms:printer-changed', refreshServiceStatus)
})
</script>
