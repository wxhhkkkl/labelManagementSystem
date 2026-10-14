/**
 * T071：分配表单的可用量校验。
 *
 * 先写并运行至失败，再由 src/utils/allocation.ts 实现至通过。
 */

import { describe, expect, it } from 'vitest'

import {
  confirmText,
  isValid,
  validateAllocation,
  validateCodeRange,
  type AllocationForm,
} from '../../src/utils/allocation'

function form(overrides: Partial<AllocationForm> = {}): AllocationForm {
  return { company_id: 7, product_id: 3, quantity: 100, ...overrides }
}

describe('validateAllocation', () => {
  it('accepts a well-formed form', () => {
    expect(validateAllocation(form(), 500)).toEqual({})
  })

  it('requires a company', () => {
    expect(validateAllocation(form({ company_id: null }), 500).company_id).toBeTruthy()
  })

  it('requires a product', () => {
    expect(validateAllocation(form({ product_id: null }), 500).product_id).toBeTruthy()
  })

  it('requires a quantity', () => {
    expect(validateAllocation(form({ quantity: null }), 500).quantity).toBeTruthy()
  })

  it('rejects zero and negative quantities', () => {
    expect(validateAllocation(form({ quantity: 0 }), 500).quantity).toBeTruthy()
    expect(validateAllocation(form({ quantity: -5 }), 500).quantity).toBeTruthy()
  })

  it('rejects fractional quantities', () => {
    expect(validateAllocation(form({ quantity: 1.5 }), 500).quantity).toContain('整数')
  })

  it('rejects quantity above available stock and says the number', () => {
    const errors = validateAllocation(form({ quantity: 600 }), 500)
    expect(errors.quantity).toContain('500')
  })

  it('accepts quantity exactly equal to available stock', () => {
    expect(validateAllocation(form({ quantity: 500 }), 500)).toEqual({})
  })

  it('skips the stock check when available is unknown', () => {
    // 尚未查出可用量时不该拦下用户，交给服务端判定
    expect(validateAllocation(form({ quantity: 999999 }), null)).toEqual({})
  })

  it('reports company and product problems together', () => {
    const errors = validateAllocation(
      { company_id: null, product_id: null, quantity: 10 },
      500,
    )
    expect(Object.keys(errors).sort()).toEqual(['company_id', 'product_id'])
  })
})

describe('validateCodeRange', () => {
  it('accepts an ordered range', () => {
    expect(validateCodeRange('A001', 'A999')).toBeNull()
  })

  it('accepts a half-open range', () => {
    expect(validateCodeRange('A001', undefined)).toBeNull()
    expect(validateCodeRange(undefined, 'A999')).toBeNull()
  })

  it('rejects a reversed range', () => {
    expect(validateCodeRange('B001', 'A001')).toContain('不能大于')
  })
})

describe('confirmText', () => {
  it('mentions quantity, product and company', () => {
    const text = confirmText(form(), '华东分公司', '500ml 矿泉水')
    expect(text).toContain('100')
    expect(text).toContain('500ml 矿泉水')
    expect(text).toContain('华东分公司')
  })

  it('includes the code range when given', () => {
    const text = confirmText(form({ code_range_from: 'A001', code_range_to: 'A500' }), '甲', '乙')
    expect(text).toContain('A001')
    expect(text).toContain('A500')
  })

  it('omits the range clause when not given', () => {
    expect(confirmText(form(), '甲', '乙')).not.toContain('码段')
  })
})

describe('isValid', () => {
  it('is true only without errors', () => {
    expect(isValid({})).toBe(true)
    expect(isValid({ quantity: 'x' })).toBe(false)
  })
})
