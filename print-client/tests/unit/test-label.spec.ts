import { describe, expect, it } from 'vitest'
import { testLabel } from '../../src/renderer/utils/testLabel'
import { renderToString } from '../../src/print-render/renderer'
import type { TemplatePreview } from '../../src/renderer/api/print'

describe('使用当前模板测试打印',()=>{
  const template:TemplatePreview={name:'当前模板',version_no:2,elements_json:{paper_width_mm:60,paper_height_mm:30,elements:[
    {type:'text',x:1,y:1,width:30,height:4,font_size:3,content:'当前模板标题',rotation:90},
    {type:'barcode',x:1,y:6,width:30,height:8,symbology:'ean13',field_name:'code_value'},
    {type:'field',x:1,y:15,width:40,height:4,font_size:3,field_name:'production_batch_no'},
    {type:'date',x:1,y:20,width:25,height:4,font_size:3},
    {type:'serial',x:30,y:20,width:20,height:4,font_size:3,serial_digits:5},
  ]},data:{code_value:'6901234567892',production_batch_no:'REAL-BATCH',print_date:'2026-01-01',serial_no:'123'}}
  it('保留当前模板尺寸、排版与旋转属性，不修改原模板或真实数据',()=>{
    const original=JSON.stringify(template)
    const job=testLabel(template,new Date('2026-10-18T18:00:00Z'))
    expect(job.doc).toEqual(template.elements_json)
    expect(job.doc).not.toBe(template.elements_json)
    expect(job.data).toMatchObject({code_value:'0000000000000',production_batch_no:'TEST-ONLY',print_date:'2026-10-19',serial_no:'0'})
    expect(JSON.stringify(template)).toBe(original)
  })
  it('日期和编号为测试值，条码可正常生成且不会输出真实码或批号',()=>{
    const job=testLabel(template,new Date('2026-10-18T00:00:00Z'))
    const html=renderToString(job.doc,job.data)
    expect(html).toContain('当前模板标题')
    expect(html).toContain('TEST-ONLY')
    expect(html).toContain('00000')
    expect(html).not.toContain('REAL-BATCH')
    expect(html).not.toContain('6901234567892')
  })
})
