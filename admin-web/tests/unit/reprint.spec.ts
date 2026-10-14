/**
 * T105：补打/作废原因必填校验。
 *
 * 先写并运行至失败，再由 src/utils/reprint.ts 实现至通过。
 */

import { describe, expect, it } from 'vitest'

import {
  REASON_MAX_LENGTH,
  explainError,
  isValid,
  ledgerKindLabel,
  taskStatusLabel,
  validateReason,
  validateReprint,
  validateVoid,
  voidConfirmText,
} from '../../src/utils/reprint'

describe('validateReason', () => {
  it('accepts a normal reason', () => {
    expect(validateReason('标签破损')).toBeNull()
  })

  it('rejects empty and missing reasons', () => {
    expect(validateReason('')).toBeTruthy()
    expect(validateReason(null)).toBeTruthy()
    expect(validateReason(undefined)).toBeTruthy()
  })

  it('treats whitespace-only as unfilled', () => {
    // 服务端也是 trim 后判空，前端必须一致，否则会白跑一次被拒的请求
    expect(validateReason('   ')).toBeTruthy()
    expect(validateReason('\t\n')).toBeTruthy()
  })

  it('accepts a reason padded with spaces', () => {
    expect(validateReason('  标签破损  ')).toBeNull()
  })

  it('rejects reasons beyond the length limit', () => {
    expect(validateReason('x'.repeat(REASON_MAX_LENGTH))).toBeNull()
    expect(validateReason('x'.repeat(REASON_MAX_LENGTH + 1))).toContain(String(REASON_MAX_LENGTH))
  })
})

describe('validateVoid', () => {
  it('accepts a selection with a reason', () => {
    expect(validateVoid({ codeValues: ['A001'], reason: '整批报废' })).toEqual({})
  })

  it('requires at least one code', () => {
    expect(validateVoid({ codeValues: [], reason: '报废' }).codeValues).toBeTruthy()
  })

  it('requires a reason even when codes are selected', () => {
    const errors = validateVoid({ codeValues: ['A001', 'A002'], reason: '  ' })
    expect(errors.reason).toBeTruthy()
    expect(errors.codeValues).toBeUndefined()
  })

  it('reports both problems at once', () => {
    const errors = validateVoid({ codeValues: [], reason: '' })
    expect(Object.keys(errors).sort()).toEqual(['codeValues', 'reason'])
  })
})

describe('validateReprint', () => {
  it('accepts a chosen code with a reason', () => {
    expect(validateReprint({ codeValue: 'A001', reason: '破损' })).toEqual({})
  })

  it('requires a code', () => {
    expect(validateReprint({ codeValue: null, reason: '破损' }).codeValue).toBeTruthy()
  })

  it('requires a reason', () => {
    expect(validateReprint({ codeValue: 'A001', reason: '   ' }).reason).toBeTruthy()
  })
})

describe('voidConfirmText', () => {
  it('states the count and the reason', () => {
    const text = voidConfirmText(3, '整批报废')
    expect(text).toContain('3')
    expect(text).toContain('整批报废')
  })

  it('warns that voiding is irreversible', () => {
    // 作废是终态，确认文案必须把后果讲清楚
    expect(voidConfirmText(1, 'x')).toContain('不可恢复')
  })
})

describe('explainError', () => {
  it('adds a hint for offline workstations', () => {
    const text = explainError('WORKSTATION_OFFLINE', '无法补打')
    expect(text).toContain('无法补打')
    expect(text).toContain('离线')
  })

  it('explains why a code cannot be reprinted', () => {
    expect(explainError('CODE_NOT_PRINTED', '失败')).toContain('已打印')
  })

  it('passes unknown codes through unchanged', () => {
    expect(explainError('SOMETHING_ELSE', '原始信息')).toBe('原始信息')
  })
})

describe('labels', () => {
  it('translates ledger kinds', () => {
    expect(ledgerKindLabel('reprint')).toBe('补打')
    expect(ledgerKindLabel('void')).toBe('作废')
    expect(ledgerKindLabel('other')).toBe('other')
  })

  it('translates task statuses', () => {
    expect(taskStatusLabel('pending')).toBe('待领取')
    expect(taskStatusLabel('succeeded')).toBe('已补打')
    expect(taskStatusLabel('expired')).toBe('已过期')
    expect(taskStatusLabel('weird')).toBe('weird')
  })
})

describe('isValid', () => {
  it('is true only without errors', () => {
    expect(isValid({})).toBe(true)
    expect(isValid({ reason: 'x' })).toBe(false)
  })
})
