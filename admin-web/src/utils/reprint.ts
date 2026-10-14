/**
 * 补打与作废的表单校验。
 *
 * 与组件解耦以便单测覆盖（T105）。这里只做**提交前提示**：
 * 权限、码状态、工位在线与否都由服务端判定，前端算不出来。
 */

export type Errors = Record<string, string>

/** 原因常用取值，减少手打；仍允许自由输入。 */
export const REASON_PRESETS = [
  '标签破损',
  '标签丢失',
  '打印模糊需重印',
  '整批报废',
  '产品信息变更',
] as const

export const REASON_MAX_LENGTH = 255

/**
 * 补打/作废的原因校验。
 *
 * 全空白 MUST 视为未填——服务端也是这么判断的（trim 后为空即拒）。
 * 只在提交按钮上做 disabled 是不够的：用户可能先填了空格再提交。
 */
export function validateReason(reason: string | null | undefined): string | null {
  if (reason === null || reason === undefined || reason.trim() === '') {
    return '必须填写原因'
  }
  if (reason.trim().length > REASON_MAX_LENGTH) {
    return `原因不能超过 ${REASON_MAX_LENGTH} 个字符`
  }
  return null
}

export interface VoidForm {
  /** 已勾选的码值 */
  codeValues: string[]
  reason: string
}

export function validateVoid(form: VoidForm): Errors {
  const errors: Errors = {}
  if (form.codeValues.length === 0) {
    errors.codeValues = '请至少选择一个码'
  }
  const reasonError = validateReason(form.reason)
  if (reasonError) errors.reason = reasonError
  return errors
}

export interface ReprintForm {
  codeValue: string | null
  reason: string
}

export function validateReprint(form: ReprintForm): Errors {
  const errors: Errors = {}
  if (!form.codeValue) {
    errors.codeValue = '请先选择要补打的码'
  }
  const reasonError = validateReason(form.reason)
  if (reasonError) errors.reason = reasonError
  return errors
}

export function isValid(errors: Errors): boolean {
  return Object.keys(errors).length === 0
}

/**
 * 作废确认文案。
 *
 * 作废是**不可恢复**的终态，因此要在确认框里把后果和数量都说清楚，
 * 不能让用户在不知情的情况下点下去。
 */
export function voidConfirmText(count: number, reason: string): string {
  return `将作废 ${count} 个码，作废后不可恢复、不可打印。原因：${reason.trim()}`
}

/**
 * 把接口错误码翻译成操作员能理解的话。
 *
 * 服务端返回的 message 通常已经够清楚，这里只兜底几个容易困惑的场景。
 */
export function explainError(errorCode: string, fallback: string): string {
  switch (errorCode) {
    case 'WORKSTATION_OFFLINE':
      return `${fallback}（原工位离线，请让工位软件恢复联网并上报心跳后重试）`
    case 'WORKSTATION_DISABLED':
      return `${fallback}（原工位或其所属公司已停用）`
    case 'CODE_NOT_PRINTED':
      return `${fallback}（只有已打印的码可以补打）`
    case 'CODE_VOIDED':
      return `${fallback}（该码已作废，不可再操作）`
    case 'FORBIDDEN_SCOPE':
      return `${fallback}（无权操作其他公司的数据）`
    default:
      return fallback
  }
}

/** 台账行的类型标签。 */
export function ledgerKindLabel(kind: string): string {
  return kind === 'reprint' ? '补打' : kind === 'void' ? '作废' : kind
}

/** 补打任务状态标签。 */
export function taskStatusLabel(status: string): string {
  return (
    {
      pending: '待领取',
      claimed: '已领取',
      succeeded: '已补打',
      failed: '补打失败',
      expired: '已过期',
    }[status] ?? status
  )
}
