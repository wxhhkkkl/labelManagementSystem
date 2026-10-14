/**
 * 分配表单的校验与提示逻辑。
 *
 * 与组件解耦以便单测覆盖（T071）。这里是**提交前提示**，
 * 权威校验在服务端——可用量要按真实库存判定，前端算的只是缓存值。
 */

export interface AllocationForm {
  company_id: number | null
  product_id: number | null
  quantity: number | null
  batch_id?: number | null
  code_range_from?: string
  code_range_to?: string
}

export type Errors = Record<string, string>

/**
 * 校验分配表单。
 *
 * `available` 为该产品当前可分配量（可为 null 表示尚未查出）。
 * 余量不足属于**可预期的业务结果**，服务端会返回 409；
 * 这里提前提示能省一次往返，但不作为拦截的唯一依据。
 */
export function validateAllocation(form: AllocationForm, available: number | null): Errors {
  const errors: Errors = {}

  if (form.company_id === null || form.company_id === undefined) {
    errors.company_id = '必须选择目标公司'
  }
  if (form.product_id === null || form.product_id === undefined) {
    errors.product_id = '必须选择产品'
  }

  const qty = form.quantity
  if (qty === null || qty === undefined) {
    errors.quantity = '请填写分配数量'
    return errors
  }
  if (!Number.isInteger(qty)) {
    errors.quantity = '分配数量必须是整数'
    return errors
  }
  if (qty <= 0) {
    errors.quantity = '分配数量必须大于 0'
    return errors
  }
  if (available !== null && qty > available) {
    errors.quantity = `可分配数量不足：当前可用 ${available}`
  }

  return errors
}

export function isValid(errors: Errors): boolean {
  return Object.keys(errors).length === 0
}

/** 码段范围：起止都填时，起必须不大于止。 */
export function validateCodeRange(from: string | undefined, to: string | undefined): string | null {
  if (from && to && from > to) return '码段起值不能大于止值'
  return null
}

/** 提交前的确认文案。数量较大时给用户一次复核机会。 */
export function confirmText(form: AllocationForm, companyName: string, productName: string): string {
  const range =
    form.code_range_from || form.code_range_to
      ? `（码段 ${form.code_range_from || '不限'} ~ ${form.code_range_to || '不限'}）`
      : ''
  return `确认从码池取 ${form.quantity} 个「${productName}」的码分配给「${companyName}」${range}？`
}
