<template>
  <section class="tasks">
    <header class="head">
      <h3>补打任务</h3>
      <span class="hint">
        {{ polling ? '每 5 秒自动领取' : '未在轮询' }}
        <template v-if="lastError"> · {{ lastError }}</template>
      </span>
    </header>

    <el-empty v-if="!queue.length" description="暂无补打任务" :image-size="40" />

    <el-table v-else :data="queue" height="100%" border size="small">
      <el-table-column prop="code_value" label="码值" width="220" />
      <el-table-column prop="product_name" label="产品" />
      <el-table-column prop="reason" label="补打原因" />
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" type="primary" :loading="busyId === row.task_id" @click="execute(row)">
            打印
          </el-button>
          <el-button size="small" link @click="fail(row)">标记失败</el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { ApiError } from '../api/client'
import { print } from '../api/print-service'
import { request } from '../api/client'
import { useTaskPolling, type ReprintTask } from '../composables/useTaskPolling'

const props = defineProps<{
  workstationId: number
  printerName: string
  serviceOk: boolean
}>()

const queue = ref<ReprintTask[]>([])
const busyId = ref<number | null>(null)

const { polling, lastError, start, poll } = useTaskPolling(
  () => props.workstationId,
  (tasks) => {
    // 去重：同一任务不会重复入队（服务端已保证不重复派发）
    const known = new Set(queue.value.map((t) => t.task_id))
    queue.value = [...queue.value, ...tasks.filter((t) => !known.has(t.task_id))]
  },
)

const hasTasks = computed(() => queue.value.length > 0)

function remove(taskId: number): void {
  queue.value = queue.value.filter((t) => t.task_id !== taskId)
}

async function execute(task: ReprintTask): Promise<void> {
  busyId.value = task.task_id
  try {
    if (!props.serviceOk || !props.printerName) {
      ElMessage.warning('请先在工位状态选择可用打印机')
      return
    }

    const outcome = await print({
      doc: task.elements_json,
      data: task.data,
      deviceName: props.printerName,
    })

    // 无论成败都要回报，否则任务会一直挂在 claimed
    await request(`/api/v1/workstation/tasks/${task.task_id}/result?workstation_id=${props.workstationId}`, {
      method: 'POST',
      json: {
        result: outcome.ok ? 'succeeded' : 'failed',
        failure_reason: outcome.ok ? null : (outcome.error ?? '打印服务报错'),
      },
    })

    if (outcome.ok) {
      ElMessage.success(`已补打 ${task.code_value}`)
      remove(task.task_id)
    } else {
      ElMessage.error(`补打失败：${outcome.error ?? '未知原因'}`)
      remove(task.task_id)
    }
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.body.message : '补打执行失败')
  } finally {
    busyId.value = null
  }
}

async function fail(task: ReprintTask): Promise<void> {
  busyId.value = task.task_id
  try {
    await request(`/api/v1/workstation/tasks/${task.task_id}/result?workstation_id=${props.workstationId}`, {
      method: 'POST',
      json: { result: 'failed', failure_reason: '操作员标记失败' },
    })
    ElMessage.warning('已标记失败，任务结束')
    remove(task.task_id)
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.body.message : '回报失败')
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  start()
  void poll()
})

defineExpose({ hasTasks, refresh: poll })
</script>

<style scoped>
.tasks {
  margin-top: 0;
}
.head {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.hint {
  font-size: 12px;
  color: #888;
}
</style>
