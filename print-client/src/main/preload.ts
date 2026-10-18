/**
 * preload：把本地打印服务的端口与令牌交给渲染层。
 *
 * 暴露打印配置和受限业务请求，不开放通用 Node 能力（contextIsolation: true）。
 * 令牌是启动时随机生成的，本机其他程序拿不到——避免被扫端口驱动打印机。
 */

import { contextBridge, ipcRenderer } from 'electron'
import type { ServiceRequest } from '../serviceConfig'

contextBridge.exposeInMainWorld('lmsBridge', {
  apiRequest: (request: ServiceRequest) => ipcRenderer.invoke('lms:service-request', request),
  machineId: process.argv.find(arg => arg.startsWith('--lms-machine-id='))?.slice('--lms-machine-id='.length) ?? String(process.env.LMS_MACHINE_ID ?? ''),
  printServicePort: Number(process.env.LMS_PRINT_PORT ?? 0),
  printServiceToken: String(process.env.LMS_PRINT_TOKEN ?? ''),
})
