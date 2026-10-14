/**
 * T113：补打任务轮询（research.md R1）。
 *
 * 5 秒一次向服务端"领取"本工位的待执行任务。服务端是原子领取——
 * 同一任务不会被两个客户端拿到。
 *
 * 空轮询在服务端不产生任何写入，所以这里的频率不必进一步降下来。
 */

import { onUnmounted, ref } from 'vue'

import { request } from '../api/client'

/** 与后端 heartbeat_interval_seconds 保持一致。 */
export const TASK_POLL_INTERVAL_MS = 5000

export interface ReprintTask {
  task_id: number
  task_type: string
  code_value: string
  template_version_id: number
  /** 模板内容随任务下发，补打无需再取一次（否则多一次往返与失败点） */
  elements_json: import('../../print-render/renderer').TemplateDoc
  data: Record<string, string>
  product_name: string
  company_name: string
  reason: string
}

export function useTaskPolling(workstationId: () => number | null, onTasks: (tasks: ReprintTask[]) => void) {
  const polling = ref(false)
  const lastError = ref<string | null>(null)
  let timer: ReturnType<typeof setInterval> | null = null

  async function poll(): Promise<void> {
    const id = workstationId()
    if (!id) return
    try {
      const body = await request<{ tasks: ReprintTask[] }>(
        `/api/v1/workstation/tasks?workstation_id=${id}`,
      )
      lastError.value = null
      if (body.tasks.length) onTasks(body.tasks)
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error)
    }
  }

  function start(): void {
    if (timer !== null) return
    polling.value = true
    void poll()
    timer = setInterval(() => void poll(), TASK_POLL_INTERVAL_MS)
  }

  function stop(): void {
    polling.value = false
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  onUnmounted(stop)

  return { polling, lastError, start, stop, poll }
}
