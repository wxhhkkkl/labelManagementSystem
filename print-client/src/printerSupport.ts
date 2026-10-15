/** 下载入口核对日期：2026-10-15。使用发布方型号页，避免安装包版本更新后链接失效。 */
export const printerGuides = [
  {
    id:'zenpert-4t200', name:'先擘 4T200', model:'Zenpert 4T200', brand:'先擘 Zenpert',
    download:'https://www.bartendersoftware.com/cn/resources/printer-drivers/zenpert/zenpert-4t200',
    support:'https://zenpert.cn/h-col-165.html', supportLabel:'先擘官方驱动中心',
    detail:'在安装向导中选择 Zenpert 4T200，按机身铭牌确认型号，勿选择 4D200 或其他系列。',
  },
  {
    id:'zenpert-4t520', name:'先擘 4T520', model:'Zenpert 4T520', brand:'先擘 Zenpert',
    download:'https://www.bartendersoftware.com/cn/resources/printer-drivers/zenpert/zenpert-4t520',
    support:'https://zenpert.cn/h-col-165.html', supportLabel:'先擘官方驱动中心',
    detail:'在安装向导中选择 Zenpert 4T520，注意 4T520 与 4D520 是不同型号。',
  },
  {
    id:'tsc-244pro', name:'TSC 244 Pro', model:'TSC TTP-244 Pro', brand:'TSC',
    download:'https://www.bartendersoftware.com/cn/resources/printer-drivers/tsc/tsc-ttp-244-pro',
    support:'https://apac.tscprinters.com/en/downloads', supportLabel:'TSC 官方下载与说明书',
    detail:'本教程对应 TTP-244 Pro。核对机身铭牌后，在向导中选择 TSC TTP-244 Pro；TTP-244、TTP-244 Plus、TTP-244M Pro 应使用各自对应型号。官方中心可搜索 TTP-244 Pro 下载说明书。',
  },
  {
    id:'datamax-m4308', name:'Datamax M-4308 Mark II', model:'Datamax M-4308 Mark II', brand:'Datamax-O’Neil',
    download:'https://www.bartendersoftware.com/resources/printer-drivers/datamax-oneil/datamax-m-4308-mark-ii',
    support:'https://sps-support.honeywell.com/s/article/How-to-download-and-install-the-latest-Honeywell-InterDriver',
    supportLabel:'Honeywell 官方驱动安装说明',
    detail:'在向导中选择 Datamax M-4308 Mark II（部分驱动显示 Datamax-O’Neil 前缀），按铭牌确认 Mark II；勿选择 I-4308 或其他 M-Class 型号。优先使用驱动包附带的 Driver Wizard。',
  },
] as const

/** 只允许内置的驱动及厂商支持页面在系统浏览器中打开。 */
export function isPrinterSupportUrl(url:string):boolean {
  return printerGuides.some(guide => guide.download === url || guide.support === url)
}
