import { expect, it } from 'vitest'
import { PrintService } from '../../src/print-service/server'

it('allows the configured station origin and preflight but still requires a token', async () => {
  const service = new PrintService({ listPrinters: async () => ['Test'], print: async () => ({ ok: true }) }, 'http://127.0.0.1:5174')
  const port = await service.start(0)
  const url = `http://127.0.0.1:${port}`
  try {
    const headers = { Origin: 'http://127.0.0.1:5174' }
    const preflight = await fetch(url + '/printers', { method: 'OPTIONS', headers })
    expect(preflight.status).toBe(204)
    expect(preflight.headers.get('access-control-allow-origin')).toBe(headers.Origin)
    expect(preflight.headers.get('access-control-allow-headers')).toContain('X-Print-Token')
    expect((await fetch(url + '/printers', { headers })).status).toBe(403)
    const printers = await fetch(url + '/printers', { headers: { ...headers, 'X-Print-Token': service.token } })
    expect(await printers.json()).toEqual({ printers: ['Test'] })
    expect((await fetch(url + '/printers', { headers: { Origin: 'https://other.example', 'X-Print-Token': service.token } })).status).toBe(403)
  } finally { await service.stop() }
})
