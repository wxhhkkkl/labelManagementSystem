<template>
  <div class="print">
    <header class="head">
      <h1>工位打印</h1>
      <span class="status" :class="serviceOk ? 'ok' : 'bad'">
        {{ serviceOk ? '打印服务正常' : '打印服务未启动' }}
      </span>
      <span v-if="boundName" class="bound">工位：{{ boundName }}</span>
    </header>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <section class="row">
      <el-select v-model="productId" placeholder="选择产品" @change="loadCodes">
        <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>

      <el-select v-model="printerName" placeholder="选择打印机">
        <el-option v-for="name in printers" :key="name" :label="name" :value="name" />
      </el-select>

      <el-input v-model="scanValue" placeholder="扫码或输入码值定位" style="width: 240px" />
      <el-button @click="locate">定位</el-button>
    </section>

    <p class="hint">
      本公司本产品共有 <strong>{{ total }}</strong> 个可打印的码。码在公司内由全部工位共享，
      不会限定到某个工位。
    </p>

    <section class="row">
      <el-input-number v-model="quantity" :min="1" :max="Math.max(total, 1)" />
      <el-button type="primary" :loading="printing" :disabled="!canPrint" @click="doPrint">
        打印
      </el-button>
    </section>

    <section>
      <h3>本次任务</h3>
      <el-table v-if="task.length" :data="task" border size="small">
        <el-table-column prop="code_value" label="码值" width="240" />
        <el-table-column label="结果" width="140">
          <template #default="{ row }">
            <el-tag :type="tagType(row)" size="small">{{ tagLabel(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="说明">
          <template #default="{ row }">{{ row.message ?? '—' }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="尚未发起打印" />

      <el-button
        v-if="hasLocked"
        type="warning"
        :loading="confirming"
        @click="doConfirmFailed"
      >
        标记失败并回退
      </el-button>
    </section>

    <TaskView
      v-if="workstationId"
      :workstation-id="workstationId"
      :printer-name="printerName"
      :service-ok="serviceOk"
    />
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { ApiError, getBoundWorkstationId } from '../api/client'
import {
  confirmPrint,
  listPrintableCodes,
  startPrint,
  scanCode,
  type AcceptedPrint,
  type PrintableCode,
} from '../api/print'
import { isPrintServiceAlive, listPrinters, print } from '../api/print-service'
import { useHeartbeat } from '../composables/useHeartbeat'
import TaskView from './TaskView.vue'

interface TaskRow {
  code_value: string
  outcome: 'accepted' | 'rejected' | 'printed' | 'rolled_back'
  message?: string
}

const workstationId = ref<number | null>(null)
const boundName = ref<string | null>(null)
const products = ref<{ id: number; name: string }[]>([])
const printers = ref<string[]>([])
const productId = ref<number | null>(null)
const printerName = ref<string>('')
const scanValue = ref('')
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
  () => !!workstationId.value && !!productId.value && total.value > 0 && !printing.value,
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
  if (serviceOk.value && printers.value.length === 0) {
    try {
      printers.value = await listPrinters()
    } catch {
      printers.value = []
    }
  }
}

async function loadCodes(): Promise<void> {
  if (!workstationId.value || !productId.value) return
  try {
    const page = await listPrintableCodes(workstationId.value, productId.value)
    codes.value = page.items
    total.value = page.total
    quantity.value = Math.min(quantity.value, Math.max(page.total, 1))
  } catch (e) {
    fail(e, '加载可打印码失败')
  }
}

async function locate(): Promise<void> {
  if (!workstationId.value || !scanValue.value) return
  try {
    const found = await scanCode(workstationId.value, scanValue.value)
    productId.value = found.product_id
    await loadCodes()
    ElMessage.success(`已定位到 ${found.code_value}`)
  } catch (e) {
    fail(e, '定位失败')
  }
}

async function doPrint(): Promise<void> {
  if (!workstationId.value || !productId.value) return
  error.value = null
  printing.value = true

  try {
    const selected = codes.value.slice(0, quantity.value).map((c) => c.code_value)

    // 1) 预占：服务端把码置为"打印中"并返回模板
    const response = await startPrint(workstationId.value, selected, printerName.value || undefined)

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
        deviceName: printerName.value,
      })
      results.push(
        outcome.ok
          ? { code_value: item.code_value, outcome: 'succeeded' as const, printer_name: printerName.value }
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
  workstationId.value = getBoundWorkstationId()
  await refreshServiceStatus()
  if (workstationId.value) heartbeat.start()
  // 打印服务可能稍后才起来（或中途重启），定期探测而不是只测一次
  poll = setInterval(refreshServiceStatus, 5000)
})

onUnmounted(() => {
  if (poll !== null) clearInterval(poll)
  heartbeat.stop()
})
</script>

<style scoped>
.print {
  padding: 16px;
}
.head {
  display: flex;
  align-items: center;
  gap: 16px;
}
.status {
  font-size: 13px;
}
.status.ok {
  color: #2e7d32;
}
.status.bad {
  color: #c62828;
}
.bound {
  font-size: 13px;
  color: #666;
}
.row {
  display: flex;
  gap: 12px;
  margin: 12px 0;
}
.hint {
  color: #666;
  font-size: 13px;
}
</style>
