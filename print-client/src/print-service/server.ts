/**
 * T094：本地打印服务（回环 HTTP）。
 *
 * 形态说明：PRD 要求"工位软件内置本地打印服务"且可与界面进程分离检测
 * （FR-069/FR-071）。因此这里把它做成一个**只监听 127.0.0.1 的 HTTP 服务**，
 * 由 Electron 主进程启动托管；界面通过回环 HTTP 调用它。
 *
 * 与真正的打印动作解耦：服务只负责 HTTP 协议与参数校验，
 * 实际出纸由注入的 PrintDriver 完成（生产环境是 Electron 的静默打印，
 * 见 src/main/print.ts）。
 *
 * 安全：只绑回环地址，并要求一个启动时生成的一次性令牌。
 * 否则本机任何程序（甚至扫描 localhost 的网页）都能驱动打印机。
 */

import { randomBytes } from 'node:crypto'
import http from 'node:http'

export const DEFAULT_PORT = 17650

/** 意外退出后的重建延迟，留一点时间让端口释放。 */
export const RESTART_DELAY_MS = 1000

export interface PageSizeMm {
  width: number
  height: number
}

export interface PrintJob {
  /** 已渲染好的整页 HTML */
  html: string
  deviceName: string
  pageSize: PageSizeMm
}

export interface PrintOutcome {
  ok: boolean
  error?: string
}

export interface PrintDriver {
  listPrinters(): Promise<string[]>
  defaultPrinter?(): Promise<string | null>
  print(job: PrintJob): Promise<PrintOutcome>
}

export class PrintService {
  readonly token: string
  private server: http.Server | null = null
  private stopping = false
  private boundPort = DEFAULT_PORT

  constructor(private readonly driver: PrintDriver, private readonly allowedOrigin = 'null') {
    this.token = randomBytes(24).toString('hex')
  }

  get port(): number {
    const address = this.server?.address()
    return typeof address === 'object' && address ? address.port : 0
  }

  async start(port = DEFAULT_PORT): Promise<number> {
    if (this.server) return this.port

    this.boundPort = port
    this.stopping = false

    this.server = http.createServer((req, res) => {
      void this.handle(req, res)
    })
    this.server.on('close', () => this.onUnexpectedClose())
    // 只绑回环：MUST NOT 监听 0.0.0.0，否则同网段机器可访问
    await new Promise<void>((resolve, reject) => {
      this.server!.once('error', reject)
      this.server!.listen(port, '127.0.0.1', () => resolve())
    })
    return this.port
  }

  async stop(): Promise<void> {
    this.stopping = true
    const server = this.server
    if (!server) return
    await new Promise<void>((resolve) => server.close(() => resolve()))
    this.server = null
  }

  /**
   * T150：服务异常退出后自动重建监听（FR-072）。
   *
   * 端口被占用、系统休眠唤醒等情况都可能让监听意外关闭。
   * 不自动恢复的话，操作员必须重启整个软件才能继续打印——
   * 而这时屏幕上只会显示"打印服务未启动"，没人知道该做什么。
   */
  private onUnexpectedClose(): void {
    if (this.stopping) return
    setTimeout(() => {
      if (this.stopping) return
      void this.start(this.boundPort).catch(() => {
        // 重建失败就再等一轮；探测端会持续报告"服务未启动"
        this.onUnexpectedClose()
      })
    }, RESTART_DELAY_MS)
  }

  private async handle(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
    const url = req.url ?? '/'
    res.setHeader('Access-Control-Allow-Origin', this.allowedOrigin)
    res.setHeader('Vary', 'Origin')
    if (req.headers.origin && req.headers.origin !== this.allowedOrigin) {
      return send(res, 403, { error_code: 'FORBIDDEN', message: '不允许此页面访问打印服务' })
    }
    if (req.method === 'OPTIONS') {
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Print-Token')
      res.writeHead(204)
      res.end()
      return
    }

    // 健康检查不需要令牌——它要被用来判断"打印服务是否在运行"
    if (req.method === 'GET' && url === '/health') {
      return send(res, 200, { status: 'ok', service: 'lms-print' })
    }

    if (req.headers['x-print-token'] !== this.token) {
      return send(res, 403, { error_code: 'FORBIDDEN', message: '缺少或错误的打印服务令牌' })
    }

    try {
      if (req.method === 'GET' && url === '/printers') {
        const printers = await this.driver.listPrinters()
        return send(res, 200, { printers })
      }
      if (req.method === 'GET' && url === '/default-printer') {
        return send(res, 200, { printer: await this.driver.defaultPrinter?.() ?? null })
      }

      if (req.method === 'POST' && url === '/print') {
        const body = await readJson(req)
        const problem = validateJob(body)
        if (problem) {
          return send(res, 400, { error_code: 'VALIDATION_ERROR', message: problem })
        }
        const outcome = await this.driver.print(body as PrintJob)
        return send(res, outcome.ok ? 200 : 500, outcome)
      }
    } catch (error) {
      return send(res, 500, {
        error_code: 'PRINT_SERVICE_ERROR',
        message: error instanceof Error ? error.message : String(error),
      })
    }

    send(res, 404, { error_code: 'NOT_FOUND', message: `未知路径：${url}` })
  }
}

function validateJob(body: unknown): string | null {
  const job = body as Partial<PrintJob> | null
  if (!job || typeof job !== 'object') return '请求体必须是 JSON 对象'
  if (!job.html || typeof job.html !== 'string') return '缺少已渲染的 html'
  if (!job.deviceName || typeof job.deviceName !== 'string') return '缺少 deviceName'
  const size = job.pageSize
  if (!size || !(size.width > 0) || !(size.height > 0)) return 'pageSize 必须为正的宽高（毫米）'
  return null
}

async function readJson(req: http.IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = []
  for await (const chunk of req) chunks.push(chunk as Buffer)
  const raw = Buffer.concat(chunks).toString('utf8')
  return raw ? JSON.parse(raw) : null
}

function send(res: http.ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload)
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    // 只服务本机界面，不允许任何浏览器页面跨源读取
    'Access-Control-Allow-Origin': String(res.getHeader('Access-Control-Allow-Origin') ?? 'null'),
  })
  res.end(body)
}
