/**
 * T113：工位心跳（research.md R1）。
 *
 * 5 秒一次上报。服务端用它推算工位是否离线——轮询模型下没有长连接可断，
 * "在线"这个判断完全建立在这条心跳上。因此心跳一旦停发超过 30 秒，
 * 该工位的补打就会被拒绝（FR-056）。
 *
 * 断网时不应堆积重试：下次心跳到点直接发即可，补发历史心跳没有意义，
 * 反而会把 last_heartbeat_at 写成一个过去的时间。
 */

import { onUnmounted, ref } from 'vue'

import { sendHeartbeat } from '../api/workstation'

/** 与后端 heartbeat_interval_seconds 保持一致。 */
export const HEARTBEAT_INTERVAL_MS = 5000

export function useHeartbeat(workstationId: () => number | null, printServiceOk: () => boolean) {
  const online = ref(false)
  const lastError = ref<string | null>(null)
  let timer: ReturnType<typeof setInterval> | null = null

  async function beat(): Promise<void> {
    const id = workstationId()
    if (!id) return
    try {
      await sendHeartbeat(id, printServiceOk())
      online.value = true
      lastError.value = null
    } catch (error) {
      // 单次失败不停表：恢复后下一次心跳自然会把状态拉回来
      online.value = false
      lastError.value = error instanceof Error ? error.message : String(error)
    }
  }

  function start(): void {
    if (timer !== null) return
    void beat()
    timer = setInterval(() => void beat(), HEARTBEAT_INTERVAL_MS)
  }

  function stop(): void {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  onUnmounted(stop)

  return { online, lastError, start, stop, beat }
}
