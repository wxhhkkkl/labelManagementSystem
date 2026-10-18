import { describe, expect, it, vi } from 'vitest'
import { requestService } from '../../src/main/serviceRequest'
import { SERVICE_ORIGIN, serviceUrl, type ServiceRequest } from '../../src/serviceConfig'

const request:ServiceRequest={path:'/api/v1/auth/login',method:'POST',headers:{'content-type':'application/json','x-lms-machine-id':'test-machine'},body:'{"username":"example"}'}

describe('固定部署服务请求',()=>{
  it('将相对业务路径解析到部署域名，并保留查询参数',()=>{
    expect(serviceUrl('/api/v1/workstation/binding?machine_id=test')).toBe(`${SERVICE_ORIGIN}/api/v1/workstation/binding?machine_id=test`)
  })
  it('拒绝外部地址、非业务路径和目录逃逸',()=>{
    for(const path of ['https://example.com/','//example.com/api/v1/auth/me','/health','/api/v1/../../secret','/api/v1/\\example.com'])expect(()=>serviceUrl(path)).toThrow()
  })
  it('保留鉴权与机器标识，禁止重定向并设置超时',async()=>{
    const transport=vi.fn<typeof fetch>().mockResolvedValue(new Response('{"access_token":"test"}',{status:200}))
    const response=await requestService({...request,headers:{...request.headers,authorization:'Bearer example'}},transport)
    expect(response.status).toBe(200)
    const [url,options]=transport.mock.calls[0]
    expect(url).toBe(`${SERVICE_ORIGIN}/api/v1/auth/login`)
    expect(options?.body).toBe(request.body)
    expect(new Headers(options?.headers).get('authorization')).toBe('Bearer example')
    expect(new Headers(options?.headers).get('x-lms-machine-id')).toBe('test-machine')
    expect(options?.redirect).toBe('error')
    expect(options?.signal).toBeInstanceOf(AbortSignal)
  })
  it('原样传回未登录错误和空响应，供渲染层处理业务状态',async()=>{
    const transport=vi.fn<typeof fetch>().mockResolvedValueOnce(new Response('{"error_code":"INVALID_CREDENTIALS"}',{status:401})).mockResolvedValueOnce(new Response(null,{status:204}))
    expect((await requestService(request,transport)).status).toBe(401)
    expect(await requestService(request,transport)).toMatchObject({status:204,body:''})
  })
  it('拒绝任意请求头和不支持的方法，且不会发起网络请求',async()=>{
    const transport=vi.fn<typeof fetch>()
    await expect(requestService({...request,headers:{host:'example.com'}},transport)).rejects.toThrow()
    await expect(requestService({...request,method:'CONNECT'},transport)).rejects.toThrow()
    expect(transport).not.toHaveBeenCalled()
  })
})
