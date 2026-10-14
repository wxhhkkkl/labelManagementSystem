/**
 * Electron 主进程。
 *
 * 职责：
 *  1. 拉起窗口承载工位界面
 *  2. 启动**本地打印服务**（回环 HTTP），并把端口与一次性令牌交给界面
 *  3. 提供真正的静默打印实现（src/main/print.ts）
 *
 * 启动顺序有讲究：打印服务必须先于窗口就绪，否则界面一打开就显示"打印服务未启动"。
 */

import { app, BrowserWindow } from 'electron'
import { join } from 'node:path'

import { listSystemPrinters, printHtml } from './print'
import { PrintService } from '../print-service/server'

const isDev = !!process.env.ELECTRON_RENDERER_URL

const printService = new PrintService({
  listPrinters: listSystemPrinters,
  print: (job) => printHtml(job),
})

let mainWindow: BrowserWindow | null = null

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1024,
    height: 720,
    title: '打印管理系统 · 工位软件',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isDev) {
    void win.loadURL(process.env.ELECTRON_RENDERER_URL as string)
  } else {
    void win.loadFile(join(__dirname, '../renderer/index.html'))
  }

  return win
}

void app.whenReady().then(async () => {
  const port = await printService.start()
  // 供 preload 读取并转交给渲染层
  process.env.LMS_PRINT_PORT = String(port)
  process.env.LMS_PRINT_TOKEN = printService.token

  mainWindow = createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) mainWindow = createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  void printService.stop()
})

export { printService }
