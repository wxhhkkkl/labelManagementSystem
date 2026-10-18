/** 服务器上的三个驱动安装包地址集中维护在此；收到正式地址后替换。当前保留发布方入口。 */
export const printerDownloadUrls = {
  zenpert: 'https://www.bartendersoftware.com/cn/resources/printer-drivers/zenpert/zenpert-4t200',
  tsc: 'https://www.bartendersoftware.com/cn/resources/printer-drivers/tsc/tsc-ttp-244-pro',
  datamax: 'https://www.bartendersoftware.com/resources/printer-drivers/datamax-oneil/datamax-m-4308-mark-ii',
}

/** 同品牌共用一个安装包，安装向导识别具体型号。 */
export const printerGuides = [
  {
    id:'zenpert', name:'先擘 Zenpert', model:'4T200 / 4T520', brand:'先擘',
    packageName:'Zenpert.zip', download:printerDownloadUrls.zenpert,
    support:'https://zenpert.cn/h-col-165.html', supportLabel:'先擘官方支持',
    detail:'将打印机连接电脑并开机，在向导中确认识别出的 Zenpert 4T200 或 Zenpert 4T520 与实际设备一致。两款型号使用同一个先擘驱动安装包。',
  },
  {
    id:'tsc', name:'TSC', model:'TTP-244 Pro', brand:'TSC',
    packageName:'TSC.zip', download:printerDownloadUrls.tsc,
    support:'https://apac.tscprinters.com/en/downloads', supportLabel:'TSC 官方支持',
    detail:'将打印机连接电脑并开机，在向导中确认识别出的 TSC TTP-244 Pro 与机身铭牌一致。',
  },
  {
    id:'datamax', name:'Datamax', model:'M-4308 Mark II', brand:'Datamax',
    packageName:'Datamax.zip', download:printerDownloadUrls.datamax,
    support:'https://sps-support.honeywell.com/s/article/How-to-download-and-install-the-latest-Honeywell-InterDriver',
    supportLabel:'Honeywell 官方支持',
    detail:'将打印机连接电脑并开机，在向导中确认识别出的 Datamax M-4308 Mark II 与实际设备一致；部分驱动显示 Datamax-O’Neil 前缀。',
  },
] as const

/** 只允许已配置的驱动下载与厂商支持页面在系统浏览器中打开。 */
export function isPrinterSupportUrl(url:string):boolean {
  try {
    if (!['https:', 'http:'].includes(new URL(url).protocol)) return false
  } catch { return false }
  return printerGuides.some(guide => guide.download === url || guide.support === url)
}
