/**
 * T052：导入页的进度与失败明细展示逻辑。
 *
 * 先写并运行至失败，再由 src/utils/importView.ts 实现至通过。
 */

import { describe, expect, it } from 'vitest'

import {
  POLL_INTERVAL_MS,
  canDownloadErrors,
  isFinal,
  progressPercent,
  progressText,
  statusLabel,
  statusTagType,
  validateUploadSelection,
  type BatchLike,
} from '../../src/utils/importView'

function batch(overrides: Partial<BatchLike> = {}): BatchLike {
  return {
    status: 'processing',
    total_rows: 1000,
    processed_rows: 250,
    success_count: 0,
    failure_count: 0,
    ...overrides,
  }
}

describe('statusLabel / statusTagType', () => {
  it('translates known statuses', () => {
    expect(statusLabel('pending')).toBe('排队中')
    expect(statusLabel('succeeded')).toBe('已完成')
    expect(statusLabel('failed')).toBe('已失败')
    expect(statusLabel('interrupted')).toBe('已中断')
  })

  it('falls back to the raw value for unknown statuses', () => {
    expect(statusLabel('weird')).toBe('weird')
  })

  it('maps status to a tag type', () => {
    expect(statusTagType('succeeded')).toBe('success')
    expect(statusTagType('failed')).toBe('danger')
    expect(statusTagType('interrupted')).toBe('warning')
    expect(statusTagType('processing')).toBe('info')
  })
})

describe('isFinal', () => {
  it('treats the three terminal states as final', () => {
    expect(isFinal('succeeded')).toBe(true)
    expect(isFinal('failed')).toBe(true)
    expect(isFinal('interrupted')).toBe(true)
  })

  it('keeps polling for pending and processing', () => {
    expect(isFinal('pending')).toBe(false)
    expect(isFinal('processing')).toBe(false)
  })
})

describe('progressPercent', () => {
  it('computes an integer percentage', () => {
    expect(progressPercent(batch({ processed_rows: 250, total_rows: 1000 }))).toBe(25)
  })

  it('returns 0 when total is unknown or zero', () => {
    // 解析出表头前 total_rows 为 null，进度条不能拿到 NaN
    expect(progressPercent(batch({ total_rows: null, processed_rows: 0 }))).toBe(0)
    expect(progressPercent(batch({ total_rows: 0, processed_rows: 0 }))).toBe(0)
  })

  it('never exceeds 100 even if processed overshoots total', () => {
    expect(progressPercent(batch({ processed_rows: 1200, total_rows: 1000 }))).toBe(100)
  })

  it('reports 100 for final states', () => {
    expect(progressPercent(batch({ status: 'succeeded', processed_rows: 3, total_rows: 10 }))).toBe(
      100,
    )
    expect(progressPercent(batch({ status: 'failed', total_rows: null }))).toBe(100)
  })
})

describe('progressText', () => {
  it('shows a waiting hint before processing starts', () => {
    expect(progressText(batch({ status: 'pending', total_rows: null, processed_rows: 0 }))).toContain(
      '等待',
    )
  })

  it('shows counts while processing', () => {
    expect(progressText(batch({ processed_rows: 250, total_rows: 1000 }))).toBe('已处理 250 / 1000 行')
  })

  it('explains a whole-batch rejection instead of showing zeros', () => {
    const text = progressText(
      batch({ status: 'failed', total_rows: 10, processed_rows: 10, success_count: 0, failure_count: 3 }),
    )
    expect(text).toContain('整批拒绝')
    expect(text).toContain('失败明细')
  })

  it('shows the success/failure split on success', () => {
    const text = progressText(
      batch({ status: 'succeeded', total_rows: 10, processed_rows: 10, success_count: 8, failure_count: 2 }),
    )
    expect(text).toContain('成功 8')
    expect(text).toContain('失败 2')
  })

  it('tells the user to re-upload when interrupted', () => {
    expect(progressText(batch({ status: 'interrupted' }))).toContain('重新上传')
  })
})

describe('canDownloadErrors', () => {
  it('is true only when there are failures', () => {
    expect(canDownloadErrors(batch({ failure_count: 1 }))).toBe(true)
    expect(canDownloadErrors(batch({ failure_count: 0 }))).toBe(false)
  })
})

describe('validateUploadSelection', () => {
  it('requires both files', () => {
    expect(validateUploadSelection(null, null)).toContain('同时')
    // 参数顺序是 (码清单, 对照关系)，提示必须指向缺失的那一个
    expect(validateUploadSelection(null, 'b')).toContain('码清单')
    expect(validateUploadSelection('a', null)).toContain('对照关系')
  })

  it('passes when both are present', () => {
    expect(validateUploadSelection('a', 'b')).toBeNull()
  })
})

describe('poll interval', () => {
  it('matches the 2s contract', () => {
    expect(POLL_INTERVAL_MS).toBe(2000)
  })
})
