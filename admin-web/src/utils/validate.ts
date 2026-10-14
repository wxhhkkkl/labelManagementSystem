/**
 * 组织与账号表单的纯校验逻辑。
 *
 * 刻意与组件解耦：这些规则需要被单测覆盖（T037），也必须在提交前本地拦住明显错误。
 * 注意：这里的规则只是**提前提示**，权威校验在服务端（宪章原则六：两端不交叉引用，
 * 服务端 MUST 独立复核，不得信任前端过滤结果）。
 */

export type Role = 'hq_admin' | 'sub_admin' | 'operator'

export const ROLES: readonly Role[] = ['hq_admin', 'sub_admin', 'operator']

export const ROLE_LABELS: Record<Role, string> = {
  hq_admin: '总部管理员',
  sub_admin: '子公司管理员',
  operator: '工位操作员',
}

export type Errors = Record<string, string>

export interface CompanyForm {
  code: string
  name: string
  contact?: string
  region?: string
}

export interface WorkstationForm {
  code: string
  name: string
  company_id: number | null
  printer_name?: string
}

export interface UserForm {
  username: string
  display_name: string
  password: string
  role: Role
  company_id: number | null
}

const CODE_MAX = 32
const NAME_MAX = 128
const USERNAME_MAX = 64
const PASSWORD_MIN = 6

function required(value: unknown, label: string): string | null {
  if (value === null || value === undefined) return `${label}不能为空`
  if (typeof value === 'string' && value.trim() === '') return `${label}不能为空`
  return null
}

function maxLen(value: string | undefined, limit: number, label: string): string | null {
  if (value && value.length > limit) return `${label}不能超过 ${limit} 个字符`
  return null
}

export function validateCompany(form: CompanyForm): Errors {
  const errors: Errors = {}
  const codeEmpty = required(form.code, '公司编码')
  if (codeEmpty) errors.code = codeEmpty
  else {
    const tooLong = maxLen(form.code, CODE_MAX, '公司编码')
    if (tooLong) errors.code = tooLong
  }

  const nameEmpty = required(form.name, '公司名称')
  if (nameEmpty) errors.name = nameEmpty
  else {
    const tooLong = maxLen(form.name, NAME_MAX, '公司名称')
    if (tooLong) errors.name = tooLong
  }
  return errors
}

export function validateWorkstation(form: WorkstationForm): Errors {
  const errors: Errors = {}

  const codeEmpty = required(form.code, '工位编码')
  if (codeEmpty) errors.code = codeEmpty
  else {
    const tooLong = maxLen(form.code, CODE_MAX, '工位编码')
    if (tooLong) errors.code = tooLong
  }

  const nameEmpty = required(form.name, '工位名称')
  if (nameEmpty) errors.name = nameEmpty
  else {
    const tooLong = maxLen(form.name, NAME_MAX, '工位名称')
    if (tooLong) errors.name = tooLong
  }

  if (form.company_id === null || form.company_id === undefined) {
    errors.company_id = '必须选择所属公司'
  }
  return errors
}

export function validateUser(form: UserForm, actorRole: Role, actorCompanyId: number | null): Errors {
  const errors: Errors = {}

  const usernameEmpty = required(form.username, '账号')
  if (usernameEmpty) errors.username = usernameEmpty
  else {
    const tooLong = maxLen(form.username, USERNAME_MAX, '账号')
    if (tooLong) errors.username = tooLong
  }

  if (required(form.display_name, '姓名')) errors.display_name = '姓名不能为空'

  if (!form.password) errors.password = '密码不能为空'
  else if (form.password.length < PASSWORD_MIN) {
    errors.password = `密码不能少于 ${PASSWORD_MIN} 位`
  }

  if (!ROLES.includes(form.role)) {
    errors.role = '角色不合法'
    return errors
  }

  // 与后端 FR-004 一致：总部管理员必须不属于任何分子公司
  if (form.role === 'hq_admin') {
    if (form.company_id !== null) errors.company_id = '总部管理员不得归属分子公司'
  } else if (form.company_id === null) {
    errors.company_id = '必须选择所属公司'
  }

  // 子公司管理员只能创建本公司操作员账号（FR-004）
  if (actorRole === 'sub_admin') {
    if (form.role !== 'operator') errors.role = '子公司管理员只能创建工位操作员账号'
    if (actorCompanyId !== null && form.company_id !== null && form.company_id !== actorCompanyId) {
      errors.company_id = '只能在本公司下创建账号'
    }
  }

  return errors
}

/** 表单是否通过校验。 */
export function isValid(errors: Errors): boolean {
  return Object.keys(errors).length === 0
}

/**
 * 按登录用户角色裁剪可选角色——用于渲染下拉框，避免让用户选到一个必然被拒的项。
 */
export function assignableRoles(actorRole: Role): Role[] {
  return actorRole === 'hq_admin' ? [...ROLES] : ['operator']
}
