/**
 * T149 / T150：打印服务状态监测与断线恢复。
 *
 * 每 5 秒探测一次回环打印服务，并区分两种异常：
 * 服务未启动 vs 打印机离线（FR-071）。两者处置完全不同，
 * 混成一句提示等于让操作员自己猜。
 *
 * 断线恢复：探测失败按退避重试（status.ts 的 reconnectDelayMs），
 * 服务回来后自动恢复，不需要重启界面（FR-072）。
 */

import { onUnmounted, ref } from 'vue'

import {
  HEALTH_POLL_INTERVAL_MS,
  reconnectDelayMs,
  resolveStatus,
  shouldRebindPrinter,
  type StatusResult,
} from '../../print-service/status'
import { isPrintServiceAlive, listPrinters } from '../api/print-service'
import { getBoundPrinter } from '../api/client'

export function usePrintServiceStatus() {
  const status = ref<StatusResult>({
    state: 'service_down',
    message: '正在检测打印服务…',
    canPrint: false,
  })
  const printers = ref<string[]>([])
  const needsRebind = ref(false)
  const recoveries = ref(0)

  let failures = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  let stopped = false

  async function probe(): Promise<void> {
    const alive = await isPrintServiceAlive()

    if (alive) {
      if (failures > 0) {
        // 从失败恢复到正常，记一次，便于界面提示"已重新连接"
        recoveries.value += 1
      }
      failures = 0
      try {
        printers.value = await listPrinters()
      } catch {
        printers.value = []
      }
    } else {
      failures += 1
      printers.value = []
    }

    const boundPrinter = getBoundPrinter()
    status.value = resolveStatus({
      serviceAlive: alive,
      boundPrinter,
      availablePrinters: printers.value,
    })
    needsRebind.value = shouldRebindPrinter({
      serviceAlive: alive,
      boundPrinter,
      availablePrinters: printers.value,
    })

    schedule()
  }

  function schedule(): void {
    if (stopped) return
    if (timer !== null) clearTimeout(timer)
    // 失败时按退避拉长间隔；正常时保持固定心跳
    const delay = failures === 0 ? HEALTH_POLL_INTERVAL_MS : reconnectDelayMs(failures)
    timer = setTimeout(() => void probe(), delay)
  }

  function start(): void {
    stopped = false
    void probe()
  }

  function stop(): void {
    stopped = true
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  onUnmounted(stop)

  return { status, printers, needsRebind, recoveries, start, stop, probe }
}
