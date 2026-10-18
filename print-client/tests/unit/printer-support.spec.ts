import { describe, expect, it } from 'vitest'
import {
  DRIVER_BASE_URL,
  isPrinterSupportUrl,
  printerGuides,
} from '../../src/printerSupport'

describe('打印机下载链接的外部打开边界', () => {
  it('允许三个品牌配置的驱动与厂商支持页', () => {
    expect(printerGuides).toHaveLength(3)
    for(const guide of printerGuides) {
      expect(isPrinterSupportUrl(guide.download)).toBe(true)
      expect(isPrinterSupportUrl(guide.support)).toBe(true)
    }
  })
  it('三个安装包都指向 OSS 的 lms/drivers 目录', () => {
    expect(DRIVER_BASE_URL).toBe(
      'https://maxlabelmall.oss-cn-wulanchabu.aliyuncs.com/lms/drivers/',
    )
    for (const guide of printerGuides) {
      expect(guide.download).toBe(`${DRIVER_BASE_URL}${guide.packageName}`)
    }
  })
  it('拒绝可执行协议、非内置地址和仿冒主机', () => {
    for(const url of ['file:///C:/Windows/System32/cmd.exe','javascript:alert(1)','https://www.bartendersoftware.com.evil.test/','https://example.com/setup.exe',printerGuides[0].download+'?redirect=https://example.com']) {
      expect(isPrinterSupportUrl(url)).toBe(false)
    }
  })
})
