/**
 * T095：静默打印通道。
 *
 * 走 Windows 打印驱动路径（research.md R5）：把已渲染的 HTML 交给一个隐藏窗口，
 * 用 `webContents.print({ silent: true, deviceName, pageSize })` 出纸。
 *
 * 为什么不生成 ZPL/EPL 原生指令：FR-073 要求"新型号接入以安装驱动为基础，
 * 原则上无需修改系统代码"。原生指令与具体型号强绑定，每接一个型号都要改代码；
 * 驱动路径则只要装了驱动就能用，甲方尚未提供型号清单（OI-01）时也能先推进。
 */

import { BrowserWindow } from 'electron'

export interface PageSizeMm {
  width: number
  height: number
}

export interface ElectronPrintJob {
  html: string
  deviceName: string
  pageSize: PageSizeMm
}

export async function listSystemPrinters(): Promise<string[]> {
  // 需要一个窗口实例才能查询系统打印机列表
  const probe = new BrowserWindow({ show: false, webPreferences: { sandbox: true } })
  try {
    const printers = await probe.webContents.getPrintersAsync()
    return printers.map((p) => p.name)
  } finally {
    probe.destroy()
  }
}

export function printHtml(job: ElectronPrintJob): Promise<{ ok: boolean; error?: string }> {
  return new Promise((resolve) => {
    const win = new BrowserWindow({
      show: false,
      webPreferences: { sandbox: true, offscreen: true },
    })

    let settled = false
    const finish = (result: { ok: boolean; error?: string }) => {
      if (settled) return
      settled = true
      win.destroy()
      resolve(result)
    }

    win.webContents.once('did-finish-load', () => {
      win.webContents.print(
        {
          silent: true,
          deviceName: job.deviceName,
          // 契约要求打印侧缩放恒为 100%，不跟随系统 DPI
          scaleFactor: 100,
          // 纸张按模板定义的毫米尺寸，微米为单位
          pageSize: {
            width: Math.round(job.pageSize.width * 1000),
            height: Math.round(job.pageSize.height * 1000),
          },
          margins: { marginType: 'none' },
        },
        (success, failureReason) => {
          finish(success ? { ok: true } : { ok: false, error: failureReason })
        },
      )
    })

    win.webContents.once('did-fail-load', (_e, code, description) => {
      finish({ ok: false, error: `页面加载失败（${code}）：${description}` })
    })

    void win.loadURL(
      `data:text/html;charset=utf-8,${encodeURIComponent(job.html)}`,
    )
  })
}
