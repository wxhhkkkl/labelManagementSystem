import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request, setBoundPrinter, setBoundWorkstationId, setToken, getBoundPrinter, getBoundWorkstationId } from '../../src/renderer/api/client'

afterEach(()=>vi.unstubAllGlobals())
function setup(status:number, body:string){
  const data=new Map<string,string>()
  vi.stubGlobal('localStorage',{getItem:(key:string)=>data.get(key)??null,setItem:(key:string,value:string)=>data.set(key,value),removeItem:(key:string)=>data.delete(key)})
  const apiRequest=vi.fn().mockResolvedValue({status,statusText:'',body})
  const dispatchEvent=vi.fn()
  vi.stubGlobal('window',{lmsBridge:{machineId:'test-machine',apiRequest},dispatchEvent})
  return {apiRequest,dispatchEvent}
}
describe('渲染层通过主进程访问服务',()=>{
  it('发送账号令牌、机器标识和 JSON 正文，并解析远程响应',async()=>{
    const {apiRequest}=setup(200,'{"ok":true}')
    setToken('example-token')
    expect(await request('/api/v1/workstation/heartbeat',{method:'POST',json:{workstation_id:1}})).toEqual({ok:true})
    expect(apiRequest).toHaveBeenCalledWith(expect.objectContaining({path:'/api/v1/workstation/heartbeat',method:'POST',body:'{"workstation_id":1}',headers:expect.objectContaining({authorization:'Bearer example-token','x-lms-machine-id':'test-machine','content-type':'application/json'})}))
  })
  it('保留远程错误信息并在绑定失效时清除旧工位',async()=>{
    const {dispatchEvent}=setup(403,'{"error_code":"WORKSTATION_NOT_BOUND","message":"工位已解绑","details":{}}')
    setBoundWorkstationId(1);setBoundPrinter('Printer')
    await expect(request('/api/v1/workstation/codes')).rejects.toBeInstanceOf(ApiError)
    expect(getBoundWorkstationId()).toBeNull();expect(getBoundPrinter()).toBeNull()
    expect(dispatchEvent).toHaveBeenCalledWith(expect.objectContaining({type:'lms:binding-invalid'}))
  })
  it('正确处理没有正文的心跳响应',async()=>{
    setup(204,'')
    expect(await request('/api/v1/workstation/heartbeat',{method:'POST',json:{workstation_id:1}})).toBeUndefined()
  })
})
