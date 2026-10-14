/**
 * T037：组织树与账号表单校验。
 *
 * 先写并运行至失败，再由 src/utils/validate.ts 实现至通过。
 */

import { describe, expect, it } from 'vitest'

import {
  assignableRoles,
  isValid,
  validateCompany,
  validateUser,
  validateWorkstation,
  type UserForm,
} from '../../src/utils/validate'

const baseUser: UserForm = {
  username: 'op001',
  display_name: '张三',
  password: 'pw123456',
  role: 'operator',
  company_id: 7,
}

describe('validateCompany', () => {
  it('accepts a well-formed company', () => {
    expect(validateCompany({ code: 'C001', name: '华东分公司' })).toEqual({})
  })

  it('rejects blank code and name', () => {
    const errors = validateCompany({ code: '   ', name: '' })
    expect(errors.code).toBeTruthy()
    expect(errors.name).toBeTruthy()
  })

  it('rejects code longer than 32 chars', () => {
    const errors = validateCompany({ code: 'x'.repeat(33), name: '名称' })
    expect(errors.code).toContain('32')
  })

  it('accepts exactly 32 chars', () => {
    expect(validateCompany({ code: 'x'.repeat(32), name: '名称' })).toEqual({})
  })
})

describe('validateWorkstation', () => {
  it('requires a company', () => {
    const errors = validateWorkstation({
      code: 'W001',
      name: '一号包装工位',
      company_id: null,
    })
    expect(errors.company_id).toBeTruthy()
  })

  it('accepts a complete workstation', () => {
    expect(
      validateWorkstation({ code: 'W001', name: '一号包装工位', company_id: 7 }),
    ).toEqual({})
  })
})

describe('validateUser', () => {
  it('accepts a valid operator for hq admin', () => {
    expect(validateUser(baseUser, 'hq_admin', null)).toEqual({})
  })

  it('requires password of at least 6 chars', () => {
    const errors = validateUser({ ...baseUser, password: '12345' }, 'hq_admin', null)
    expect(errors.password).toContain('6')
  })

  it('hq admin must not belong to a company', () => {
    const errors = validateUser({ ...baseUser, role: 'hq_admin' }, 'hq_admin', null)
    expect(errors.company_id).toBeTruthy()
  })

  it('non-hq roles must belong to a company', () => {
    const errors = validateUser({ ...baseUser, company_id: null }, 'hq_admin', null)
    expect(errors.company_id).toBeTruthy()
  })

  it('sub admin may only create operators', () => {
    const errors = validateUser({ ...baseUser, role: 'sub_admin' }, 'sub_admin', 7)
    expect(errors.role).toBeTruthy()
  })

  it('sub admin may not create users in another company', () => {
    const errors = validateUser({ ...baseUser, company_id: 99 }, 'sub_admin', 7)
    expect(errors.company_id).toBeTruthy()
  })

  it('sub admin may create operators in own company', () => {
    expect(validateUser(baseUser, 'sub_admin', 7)).toEqual({})
  })

  it('rejects an unknown role', () => {
    const errors = validateUser(
      { ...baseUser, role: 'superuser' as never },
      'hq_admin',
      null,
    )
    expect(errors.role).toBeTruthy()
  })
})

describe('assignableRoles', () => {
  it('hq admin can assign all three roles', () => {
    expect(assignableRoles('hq_admin')).toEqual(['hq_admin', 'sub_admin', 'operator'])
  })

  it('sub admin can only assign operator', () => {
    expect(assignableRoles('sub_admin')).toEqual(['operator'])
  })
})

describe('isValid', () => {
  it('is true only when there are no errors', () => {
    expect(isValid({})).toBe(true)
    expect(isValid({ code: '必填' })).toBe(false)
  })
})
