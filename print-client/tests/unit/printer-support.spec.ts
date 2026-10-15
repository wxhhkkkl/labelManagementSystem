import { describe, expect, it } from 'vitest'
import { isPrinterSupportUrl, printerGuides } from '../../src/printerSupport'

describe('打印机下载链接的外部打开边界', () => {
  it('允许四款型号内置的驱动与厂商支持页', () => {
    expect(printerGuides).toHaveLength(4)
    for(const guide of printerGuides) {
      expect(isPrinterSupportUrl(guide.download)).toBe(true)
      expect(isPrinterSupportUrl(guide.support)).toBe(true)
    }
  })
  it('拒绝可执行协议、非内置地址和仿冒主机', () => {
    for(const url of ['file:///C:/Windows/System32/cmd.exe','javascript:alert(1)','https://www.bartendersoftware.com.evil.test/','https://example.com/setup.exe',printerGuides[0].download+'?redirect=https://example.com']) {
      expect(isPrinterSupportUrl(url)).toBe(false)
    }
  })
})
