/**
 * 导入批次的展示逻辑。
 *
 * 与组件解耦：这些换算需要被单测覆盖（T052），也决定了轮询什么时候该停。
 * 注意：服务端才是进度与状态的权威来源，这里只做展示与轮询判定。
 */

export type BatchStatus = 'pending' | 'processing' | 'succeeded' | 'failed' | 'interrupted'

export interface BatchLike {
  status: string
  total_rows: number | null
  processed_rows: number
  success_count: number
  failure_count: number
}

const STATUS_LABELS: Record<string, string> = {
  pending: '排队中',
  processing: '处理中',
  succeeded: '已完成',
  failed: '已失败',
  interrupted: '已中断',
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

/** Element Plus 的 tag 类型，用于给状态上色。 */
export function statusTagType(status: string): 'success' | 'danger' | 'warning' | 'info' {
  switch (status) {
    case 'succeeded':
      return 'success'
    case 'failed':
      return 'danger'
    case 'interrupted':
      return 'warning'
    default:
      return 'info'
  }
}

/** 终态：轮询必须停止，否则会一直打服务端。 */
export function isFinal(status: string): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'interrupted'
}

/**
 * 进度百分比（0-100）。
 *
 * total_rows 在解析出表头前为 null，此时返回 0 而不是 NaN——
 * 进度条拿到 NaN 会渲染异常。
 */
export function progressPercent(batch: BatchLike): number {
  if (isFinal(batch.status)) return 100
  const total = batch.total_rows ?? 0
  if (total <= 0) return 0
  const done = Math.min(batch.processed_rows, total)
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)))
}

/**
 * 进度文案。整批拒绝时成功数为 0，需要明确说明原因，避免用户以为"什么都没发生"。
 */
export function progressText(batch: BatchLike): string {
  if (batch.status === 'pending') return '等待处理…'
  if (batch.status === 'interrupted') return '服务重启导致中断，请重新上传'

  const total = batch.total_rows ?? 0
  const base = `已处理 ${batch.processed_rows} / ${total} 行`
  if (!isFinal(batch.status)) return base

  if (batch.status === 'failed' && batch.success_count === 0) {
    return `${base} · 整批拒绝，可下载失败明细查看原因`
  }
  return `${base} · 成功 ${batch.success_count}，失败 ${batch.failure_count}`
}

/** 是否该展示"下载失败明细"入口。 */
export function canDownloadErrors(batch: BatchLike): boolean {
  return batch.failure_count > 0
}

/** 上传前的本地预检：两个文件缺一不可（服务端也会再校验一次）。 */
export function validateUploadSelection(codeListFile: unknown, mappingFile: unknown): string | null {
  if (!codeListFile && !mappingFile) return '请同时选择码清单文件与对照关系文件'
  if (!codeListFile) return '请选择码清单文件'
  if (!mappingFile) return '请选择"码—产品"对照关系文件'
  return null
}

/** 轮询间隔（毫秒）。research.md R3 定为 2 秒。 */
export const POLL_INTERVAL_MS = 2000
