/**
 * T149：打印服务与打印机状态的判定（FR-071）。
 *
 * 契约要求区分两种异常并给出**各自明确**的提示：
 *   - 本地打印服务未启动
 *   - 打印机离线
 * 这两种的处置完全不同（前者要重启软件，后者要检查设备与线缆），
 * 把提示混成一句"无法打印"等于让操作员自己猜。
 *
 * 纯函数，便于单测覆盖（T146）。
 */

export type PrintServiceState =
  | 'ok'
  | 'service_down'
  | 'no_printer_bound'
  | 'printer_offline'

export interface StatusInput {
  /** 回环打印服务是否可达 */
  serviceAlive: boolean
  /** 本工位已绑定的打印机名；未绑定为空 */
  boundPrinter: string | null
  /** 本机当前可用的打印机清单 */
  availablePrinters: string[]
}

export interface StatusResult {
  state: PrintServiceState
  /** 给操作员看的提示 */
  message: string
  /** 是否可以直接发起打印 */
  canPrint: boolean
}

const MESSAGES: Record<PrintServiceState, string> = {
  ok: '打印服务正常',
  service_down: '打印服务未启动，请重新启动工位软件',
  no_printer_bound: '尚未绑定打印机，请先在设置中选择本机打印机',
  printer_offline: '已绑定的打印机当前不在线，请检查设备电源与连接',
}

export function resolveStatus(input: StatusInput): StatusResult {
  // 顺序有讲究：服务没起来就谈不上打印机状态，先报更根本的那个
  if (!input.serviceAlive) {
    return { state: 'service_down', message: MESSAGES.service_down, canPrint: false }
  }

  if (!input.boundPrinter) {
    return { state: 'no_printer_bound', message: MESSAGES.no_printer_bound, canPrint: false }
  }

  const online = input.availablePrinters.includes(input.boundPrinter)
  if (!online) {
    return { state: 'printer_offline', message: MESSAGES.printer_offline, canPrint: false }
  }

  return { state: 'ok', message: MESSAGES.ok, canPrint: true }
}

/** 绑定打印机消失后是否应当提示重新选择。 */
export function shouldRebindPrinter(input: StatusInput): boolean {
  return (
    input.serviceAlive && !!input.boundPrinter && !input.availablePrinters.includes(input.boundPrinter)
  )
}

/**
 * 断线重连退避：连续失败次数越多，间隔越长。
 *
 * 上限 30 秒——无限退避会让服务恢复后用户等太久，
 * 而 5 秒一次无限重试又会在服务真的停掉时空耗资源。
 */
export function reconnectDelayMs(failureCount: number): number {
  if (failureCount <= 0) return 0
  const base = 2000
  const max = 30_000
  return Math.min(max, base * 2 ** Math.min(failureCount - 1, 4))
}

export const HEALTH_POLL_INTERVAL_MS = 5000
