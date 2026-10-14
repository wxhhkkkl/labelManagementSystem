/**
 * T148：本机打印机清单。
 *
 * **清单来自操作系统，不是服务端**（FR-070）。服务端不可能知道
 * 某台工位电脑上装了哪些打印机——让它提供清单只会在两端之间
 * 造出一份永远不同步的副本。
 *
 * 真正的枚举由 Electron 主进程完成（webContents.getPrintersAsync），
 * 本模块负责把结果规整成界面可直接用的形式。
 */

export interface RawPrinter {
  name?: string
  displayName?: string
  status?: number
  isDefault?: boolean
}

export interface PrinterInfo {
  name: string
  isDefault: boolean
}

/**
 * 规整打印机清单：去空、去重、按名称排序，默认打印机置顶。
 *
 * 排序是刻意的：同一个型号在不同机器上枚举顺序不一致，
 * 不排序会让"默认打印机"这一项在界面上跳来跳去。
 */
export function normalizePrinters(raw: RawPrinter[]): PrinterInfo[] {
  const seen = new Map<string, PrinterInfo>()

  for (const printer of raw ?? []) {
    // 有的驱动只给 displayName，有的只给 name，取到哪个用哪个
    const name = (printer.name ?? printer.displayName ?? '').trim()
    if (!name || seen.has(name)) continue
    seen.set(name, { name, isDefault: printer.isDefault === true })
  }

  return [...seen.values()].sort((a, b) => {
    if (a.isDefault !== b.isDefault) return a.isDefault ? -1 : 1
    return a.name.localeCompare(b.name, 'zh-CN')
  })
}

/** 供下拉框使用：给默认打印机加个标记。 */
export function printerLabel(printer: PrinterInfo): string {
  return printer.isDefault ? `${printer.name}（默认）` : printer.name
}

/**
 * 已绑定的打印机是否还在本机清单里。
 *
 * 换了电脑、重装了驱动都会让绑定失效——界面要能立刻提示，
 * 而不是等操作员点了打印才发现打不出来。
 */
export function isPrinterAvailable(
  boundPrinter: string | null,
  printers: PrinterInfo[],
): boolean {
  if (!boundPrinter) return false
  return printers.some((printer) => printer.name === boundPrinter)
}
