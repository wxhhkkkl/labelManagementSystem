import type { TemplatePreview } from '../api/print'
import type { TemplateDoc } from '../../print-render/renderer'

/** 原样使用当前版式和尺寸，只替换演示数据；不预占业务码或申请流水号。 */
export function testLabel(template:TemplatePreview,now:Date):{doc:TemplateDoc;data:Record<string,string>} {
  const date = new Intl.DateTimeFormat('en-CA',{
    timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',
  }).format(now)
  return {
    doc:JSON.parse(JSON.stringify(template.elements_json)) as TemplateDoc,
    data:{
      ...template.data,
      code_value:'0000000000000',
      production_batch_no:'TEST-ONLY',batch_no:'TEST-ONLY',
      product_name:'测试产品',company_name:'测试打印',
      print_date:date,serial_no:'0',
    },
  }
}
