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

import { app, BrowserWindow, shell, ipcMain, net } from 'electron'
import { requestService } from './serviceRequest'
import type { ServiceRequest } from '../serviceConfig'
import { isPrinterSupportUrl } from '../printerSupport'
import { join } from 'node:path'
import { loadMachineIdentity } from './machineIdentity'

import { listSystemPrinters, getDefaultSystemPrinter, printHtml } from './print'
import { PrintService } from '../print-service/server'

const isDev = !!process.env.ELECTRON_RENDERER_URL

const printService = new PrintService({
  listPrinters: listSystemPrinters,
  defaultPrinter: getDefaultSystemPrinter,
  print: (job) => printHtml(job),
}, process.env.ELECTRON_RENDERER_URL ? new URL(process.env.ELECTRON_RENDERER_URL).origin : 'null')

let mainWindow: BrowserWindow | null = null

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1200,
    height: 860,
    minWidth: 800,
    minHeight: 640,
    title: '打印管理系统 · 工位软件',
    icon: isDev ? join(__dirname, '../../resources/app.ico') : join(process.resourcesPath, 'app.ico'),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments: [`--lms-machine-id=${process.env.LMS_MACHINE_ID}`],
    },
  })

  win.webContents.setWindowOpenHandler(({url}) => {
    if (isPrinterSupportUrl(url)) void shell.openExternal(url).catch(error => console.error('打开驱动下载页失败', error))
    return { action: 'deny' }
  })

  if (isDev) {
    void win.loadURL(process.env.ELECTRON_RENDERER_URL as string)
  } else {
    void win.loadFile(join(__dirname, '../renderer/index.html'))
  }

  return win
}

void app.whenReady().then(async () => {
  ipcMain.handle('lms:service-request', (event, request: ServiceRequest) => {
    if (event.sender !== mainWindow?.webContents || event.senderFrame !== mainWindow.webContents.mainFrame) {
      throw new Error('无权访问业务服务')
    }
    return requestService(request, net.fetch.bind(net))
  })
  if (process.platform === 'win32') app.setAppUserModelId('com.labelmgmt.print-client')
  const machineId = loadMachineIdentity(app.getPath('appData'), app.getPath('userData'))
  process.env.LMS_MACHINE_ID = machineId
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
