import type { TemplateDoc } from '../../print-render/renderer'

/** 独立测试标签，不调用业务码预占或确认接口。 */
export function testLabel(now: Date): {doc:TemplateDoc;data:Record<string,string>} {
  return {
    doc:{paper_width_mm:40,paper_height_mm:55,elements:[
      {type:'text',x:3,y:3,width:34,height:6,font_size:4,bold:true,align:'center',content:'测试打印'},
      {type:'qrcode',x:9,y:12,size:22,field_name:'test_code'},
      {type:'text',x:3,y:37,width:34,height:5,font_size:2.5,align:'center',content:'仅供打印测试'},
      {type:'field',x:2,y:44,width:36,height:4,font_size:2,align:'center',field_name:'test_time'},
    ]},
    data:{test_code:`LMS-TEST-${now.getTime()}`,test_time:now.toLocaleString('zh-CN',{hour12:false})},
  }
}
