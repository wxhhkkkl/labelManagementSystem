/**
 * preload：把本地打印服务的端口与令牌交给渲染层。
 *
 * 只暴露这两个值，不开放任何 Node 能力（contextIsolation: true, nodeIntegration: false）。
 * 令牌是启动时随机生成的，本机其他程序拿不到——避免被扫端口驱动打印机。
 */

import { contextBridge } from 'electron'

contextBridge.exposeInMainWorld('lmsBridge', {
  printServicePort: Number(process.env.LMS_PRINT_PORT ?? 0),
  printServiceToken: String(process.env.LMS_PRINT_TOKEN ?? ''),
})
