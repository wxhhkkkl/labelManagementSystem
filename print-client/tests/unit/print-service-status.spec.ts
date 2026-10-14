/**
 * T146：打印服务与打印机状态判定（FR-071 / FR-072）。
 *
 * 先写并运行至失败，再由 src/print-service/status.ts 实现至通过。
 * 重点是**两种异常必须给出不同提示**——混成一句等于让操作员自己猜。
 */

import { describe, expect, it } from 'vitest'

import {
  HEALTH_POLL_INTERVAL_MS,
  reconnectDelayMs,
  resolveStatus,
  shouldRebindPrinter,
  type StatusInput,
} from '../../src/print-service/status'

function input(overrides: Partial<StatusInput> = {}): StatusInput {
  return {
    serviceAlive: true,
    boundPrinter: 'Zebra ZD421',
    availablePrinters: ['Zebra ZD421', 'Microsoft Print to PDF'],
    ...overrides,
  }
}

describe('resolveStatus', () => {
  it('reports ok when everything is in place', () => {
    const result = resolveStatus(input())
    expect(result.state).toBe('ok')
    expect(result.canPrint).toBe(true)
  })

  it('reports service_down when the print service is unreachable', () => {
    const result = resolveStatus(input({ serviceAlive: false }))
    expect(result.state).toBe('service_down')
    expect(result.canPrint).toBe(false)
  })

  it('mentions the print service specifically, not printers', () => {
    const result = resolveStatus(input({ serviceAlive: false }))
    expect(result.message).toContain('打印服务')
    expect(result.message).not.toContain('离线')
  })

  it('reports no_printer_bound when nothing is selected', () => {
    const result = resolveStatus(input({ boundPrinter: null }))
    expect(result.state).toBe('no_printer_bound')
    expect(result.message).toContain('绑定')
  })

  it('reports printer_offline when the bound printer disappeared', () => {
    const result = resolveStatus(input({ availablePrinters: ['Microsoft Print to PDF'] }))
    expect(result.state).toBe('printer_offline')
    expect(result.message).toContain('在线')
  })

  it('distinguishes the two failure kinds', () => {
    // FR-071 的核心：两种提示不能是同一句话
    const down = resolveStatus(input({ serviceAlive: false }))
    const offline = resolveStatus(input({ availablePrinters: [] }))
    expect(down.message).not.toBe(offline.message)
    expect(down.state).not.toBe(offline.state)
  })

  it('prefers service_down over printer problems', () => {
    // 服务没起来时谈打印机状态没有意义，应报更根本的那个
    const result = resolveStatus({
      serviceAlive: false,
      boundPrinter: null,
      availablePrinters: [],
    })
    expect(result.state).toBe('service_down')
  })

  it('treats an empty printer list as printer offline, not service down', () => {
    const result = resolveStatus(input({ availablePrinters: [] }))
    expect(result.state).toBe('printer_offline')
  })
})

describe('shouldRebindPrinter', () => {
  it('is true when the bound printer vanished', () => {
    expect(shouldRebindPrinter(input({ availablePrinters: ['Other'] }))).toBe(true)
  })

  it('is false when everything is fine', () => {
    expect(shouldRebindPrinter(input())).toBe(false)
  })

  it('is false when the service itself is down', () => {
    // 服务都不可达时没法判断打印机在不在，不该提示重新绑定
    expect(shouldRebindPrinter(input({ serviceAlive: false, availablePrinters: [] }))).toBe(false)
  })

  it('is false when no printer is bound yet', () => {
    expect(shouldRebindPrinter(input({ boundPrinter: null }))).toBe(false)
  })
})

describe('reconnectDelayMs', () => {
  it('reconnects immediately on the first attempt', () => {
    expect(reconnectDelayMs(0)).toBe(0)
    expect(reconnectDelayMs(1)).toBe(2000)
  })

  it('backs off exponentially', () => {
    expect(reconnectDelayMs(2)).toBe(4000)
    expect(reconnectDelayMs(3)).toBe(8000)
  })

  it('caps the delay so recovery is not delayed forever', () => {
    expect(reconnectDelayMs(10)).toBe(30_000)
    expect(reconnectDelayMs(1000)).toBe(30_000)
  })

  it('never returns a negative delay', () => {
    expect(reconnectDelayMs(-5)).toBe(0)
  })
})

describe('poll interval', () => {
  it('matches the 5s heartbeat contract', () => {
    expect(HEALTH_POLL_INTERVAL_MS).toBe(5000)
  })
})
