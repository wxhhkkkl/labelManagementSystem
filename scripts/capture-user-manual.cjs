/** 用当前真实页面与演示接口生成使用说明截图，不访问业务数据或真实打印机。 */
const {chromium}=require('../admin-web/node_modules/@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const output=path.join(__dirname,'../admin-web/public/manual');
fs.mkdirSync(output,{recursive:true});
const date='2026-10-16T02:00:00Z';
const doc=JSON.parse(fs.readFileSync(path.join(__dirname,'../docs/templates/certificate-40x55.json'),'utf8'));
const company={id:1,code:'DEMO-EAST',name:'示例华东分公司',contact:'示例联系人',region:'华东',status:'active'};
const station={id:1,workstation_id:1,code:'DEMO-WS01',name:'华东一号打印台',company_id:1,company_name:company.name,printer_name:'Zenpert 4T200',status:'active',online:true,machine_bound:true,last_heartbeat_at:date,operator_ids:[]};
const stations=[station,{...station,id:2,workstation_id:2,code:'DEMO-WS02',name:'华东二号打印台',online:false,machine_bound:false,printer_name:null}];
const product={id:1,code:'DEMO-P01',name:'示例板材',spec:'标准型',default_template_id:1,status:'active',stats:{imported:1000,allocated:200,printed:20}};
const template={id:1,code:'CERTIFICATE_40X55',name:'合格证（40×55mm·LOGO留白）',status:'active',current_version_no:1,version_count:1};
const codes=['000123456789012345','000123456789012346','000123456789012347'].map((code_value,index)=>({id:index+1,code_value,production_batch_no:'DEMO-20261016-A',status:index===2?'printed':'allocated',product_id:1,company_id:1,import_batch_id:1,print_count:index===2?1:0,reprint_count:0}));
const order={id:1,order_no:'ALL-DEMO-20261016-001',company_id:1,company_name:company.name,product_id:1,product_name:product.name,code_count:200,template_name:template.name,template_version_id:1,status:'active'};
const data={code_value:codes[0].code_value,production_batch_no:'DEMO-20261016-A',product_name:product.name,company_name:company.name,print_date:'2026-10-16',serial_no:'1',batch_no:order.order_no};
const batch={id:1,batch_no:'IMP-DEMO-20261016-001',product_id:1,product_names:[product.name],status:'succeeded',total_rows:1000,processed_rows:1000,success_count:1000,failure_count:0,created_at:date,finished_at:date};
const printDetails=[{code_value:codes[2].code_value,product_name:product.name,company_name:company.name,workstation_name:station.name,operator_name:'示例操作员',printer_name:station.printer_name,print_type:'first',result:'succeeded',failure_reason:null,printed_at:date}];
let role='hq_admin';
const profile=()=>({id:role==='hq_admin'?1:2,username:role==='hq_admin'?'demo_admin':role==='sub_admin'?'demo_manager':'demo_operator',display_name:role==='hq_admin'?'示例总部管理员':role==='sub_admin'?'示例分公司管理员':'示例操作员',role,company_id:role==='hq_admin'?null:1,company:role==='hq_admin'?null:company,workstations:[]});
const tally={key:'1_1',company_name:company.name,product_name:product.name,unallocated:800,allocated:178,printing:2,printed:20,voided:0,allocated_not_printed:180,total:1000};
async function mockAdmin(route){
 const url=new URL(route.request().url()),p=url.pathname;let body;
 if(p.endsWith('/auth/me'))body=profile();
 else if(p.endsWith('/auth/login'))body={access_token:'demo-token',user:profile()};
 else if(p.endsWith('/org/tree'))body=[{...company,workstations:stations}];
 else if(p.endsWith('/companies'))body=[company];
 else if(p.endsWith('/workstations'))body=stations;
 else if(p.endsWith('/users'))body=[{...profile(),status:'active'},{id:3,username:'demo_operator',display_name:'示例操作员',role:'operator',company_id:1,status:'active'}];
 else if(p.endsWith('/products')||p.endsWith('/products/options'))body=[product];
 else if(p.endsWith('/templates'))body=[template];
 else if(p.endsWith('/templates/1/versions'))body=[{id:1,template_id:1,version_no:1,paper_width_mm:40,paper_height_mm:55,elements_json:doc,frozen:true}];
 else if(p.endsWith('/imports'))body=[batch];
 else if(p.endsWith('/allocations'))body=[order];
 else if(p.endsWith('/codes'))body={items:codes,total:3,page:1,page_size:20};
 else if(p.endsWith('/reprints'))body=[{kind:'reprint',code_value:codes[2].code_value,product_name:product.name,company_name:company.name,reason:'标签被撕破，重新打印',operator_id:2,workstation_id:1,result:'succeeded',occurred_at:date}];
 else if(p.endsWith('/reports/prints'))body=printDetails;
 else if(p.endsWith('/dashboard/code-distribution'))body={group_by:'company_product',rows:[tally],totals:tally};
 else if(p.endsWith('/audit-logs'))body=[{id:1,operator_id:1,role:'hq_admin',company_id:1,workstation_id:null,action:'allocate',target_type:'allocation_order',target_id:1,ip:'192.0.2.10',result:'success',occurred_at:date}];
 else if(p.includes('/codes/'))body={code_value:codes[2].code_value,status:'printed',status_label:'已打印',product_name:product.name,company_name:company.name,allocation_order_no:order.order_no,template_version_id:1,print_count:1,reprint_count:0,void_reason:null,timeline:[{event_type:'imported',label:'码导入',from_status_label:null,to_status_label:'待分配',operator_name:'示例总部管理员',reason:null,occurred_at:date},{event_type:'allocated',label:'分配到公司',from_status_label:'待分配',to_status_label:'已分配',operator_name:'示例总部管理员',occurred_at:date},{event_type:'printed',label:'首次打印成功',from_status_label:'打印中',to_status_label:'已打印',operator_name:'示例操作员',workstation_name:station.name,occurred_at:date}]};
 else throw new Error('未覆盖演示接口 '+p);
 await route.fulfill({json:body});
}
async function capture(page,name){
 await page.evaluate(async()=>{await document.fonts.ready;document.querySelector('#manual-demo-label')?.remove();const label=document.createElement('div');label.id='manual-demo-label';label.textContent='操作示意 · 演示数据';label.style.cssText='position:fixed;right:16px;bottom:10px;z-index:99999;background:#1745a8;color:white;font:12px Microsoft YaHei,sans-serif;padding:6px 12px;border-radius:6px;pointer-events:none';document.body.append(label)});
 await page.waitForTimeout(380);
 assert.equal(await page.locator('.el-alert--error').count(),0,'截图页面出现接口错误：'+name);
 await page.screenshot({path:path.join(output,name),animations:'disabled'});
 console.log('Captured '+name);
}
async function dialogFill(page,values){const d=page.getByRole('dialog');await d.waitFor();const inputs=d.locator('input:not([readonly])');for(let i=0;i<values.length;i++)await inputs.nth(i).fill(values[i]);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1500,height:1000},reducedMotion:'reduce'});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>localStorage.setItem('lms.access_token','manual-demo-token'));
 await page.route('**/api/v1/**',mockAdmin);
 async function go(route){await page.goto('http://127.0.0.1:5173'+route);await page.locator('.admin-main').waitFor();await page.waitForTimeout(300);}
 if(process.env.LMS_MANUAL_ONLY_IMPORT==='1') {
  await go('/imports');
  await page.locator('input[type=file]').setInputFiles({name:'产品批号表（示例）.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:Buffer.from('演示文件，仅截图')});
  await capture(page,'admin-import.png');await browser.close();return;
 }
 await page.goto('http://127.0.0.1:5173/login');await capture(page,'admin-login.png');
 await go('/org');await page.getByRole('button',{name:'新增公司',exact:true}).click();await dialogFill(page,['DEMO-EAST-02','示例华南分公司','示例负责人','华南']);await capture(page,'admin-company.png');
 await go('/workstations');await capture(page,'admin-workstation.png');await page.getByRole('button',{name:'新建工位',exact:true}).click();await dialogFill(page,['DEMO-WS03','华东三号打印台']);await capture(page,'admin-workstation-create.png');
 await go('/users');await page.getByRole('button',{name:'新建账号',exact:true}).click();await dialogFill(page,['demo_new_operator','示例新员工','ExamplePassword']);await page.getByRole('dialog').locator('.el-select__wrapper').last().click();await page.getByRole('option',{name:company.name,exact:true}).click();await capture(page,'admin-user-create.png');
 await go('/products');await page.getByRole('button',{name:'新建产品',exact:true}).click();await dialogFill(page,['DEMO-P02','示例产品二','标准型']);await capture(page,'admin-product-create.png');
 await go('/products');await page.getByRole('button',{name:'绑定模板',exact:true}).click();await capture(page,'admin-product-bind.png');
 await go('/templates');await capture(page,'admin-templates.png');await page.getByRole('button',{name:'编辑',exact:true}).click();await page.locator('.layer-row').nth(4).click();await capture(page,'admin-template-editor.png');
 await go('/imports');await page.locator('input[type=file]').setInputFiles({name:'产品批号表（示例）.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:Buffer.from('演示文件，仅截图')});await capture(page,'admin-import.png');
 await go('/allocations');await page.locator('.el-form .el-select__wrapper').first().click();await page.getByRole('option',{name:company.name,exact:true}).click();await capture(page,'admin-allocation.png');
 await go('/code-pool');await capture(page,'admin-code-pool.png');
 await go('/code-actions');await page.getByPlaceholder('输入或扫码定位单个码').fill(codes[2].code_value);await page.locator('.form input').nth(1).fill('标签被撕破，重新打印');await capture(page,'admin-reprint.png');await page.getByRole('button',{name:'作废',exact:true}).click();await page.locator('.el-message-box').waitFor();await capture(page,'admin-void.png');await page.getByRole('button',{name:'取消',exact:true}).click();
 await go('/print-details');await capture(page,'admin-print-details.png');
 await go('/ledger');await capture(page,'admin-ledger.png');
 await go('/dashboard');await capture(page,'admin-dashboard.png');
 await go('/code-timeline');await page.getByPlaceholder('输入或扫码定位码值').fill(codes[2].code_value);await page.getByRole('button',{name:'查询',exact:true}).click();await page.locator('.timeline').waitFor();await capture(page,'admin-timeline.png');
 await go('/audit-logs');await capture(page,'admin-audit.png');
 role='sub_admin';await go('/workstations');await capture(page,'admin-subadmin.png');await go('/users');await page.getByRole('button',{name:'新建员工',exact:true}).click();await dialogFill(page,['demo_employee','示例新员工','ExamplePassword']);await capture(page,'admin-employee.png');
 role='operator';
 const pc=await context.newPage();pc.on('pageerror',e=>errors.push(e.message));
 let bound=false,queue=[],mode='normal',printed=false;
 await pc.addInitScript(()=>{window.lmsBridge={machineId:'manual-demo-machine',printServicePort:17650,printServiceToken:'manual-demo-token'}});
 await pc.route('http://127.0.0.1:17650/**',async route=>{
  const p=new URL(route.request().url()).pathname;let body;
  if(p==='/printers')body={printers:['Zenpert 4T200','TSC TTP-244 Pro','Datamax M-4308 Mark II']};
  else if(p==='/default-printer')body={printer:'Zenpert 4T200'};
  else body=mode==='failure'&&p==='/print'?{ok:false,error:'打印机缺纸，请检查耗材'}:{ok:true};
  await route.fulfill({json:body,headers:{'Access-Control-Allow-Origin':'*'}});
 });
 await pc.route('**/api/v1/**',async route=>{
  const p=new URL(route.request().url()).pathname;let body;
  if(p.endsWith('/auth/login'))body={access_token:'manual-demo-token',user:profile()};
  else if(p.endsWith('/auth/me'))body=profile();
  else if(p.endsWith('/workstation/binding'))body=bound?station:null;
  else if(p.endsWith('/workstation/available'))body=[station];
  else if(p.endsWith('/products/options'))body=[product];
  else if(p.endsWith('/workstation/codes'))body={total:printed?179:180,items:codes.slice(0,2),screen_scope_note:'公司共享'};
  else if(p.endsWith('/workstation/template'))body={name:template.name,version_no:1,elements_json:doc,data:{...data,print_date:'',serial_no:''}};
  else if(p.endsWith('/workstation/tasks')){body={tasks:queue};queue=[];}
  else if(p.endsWith('/workstation/print'))body={accepted:[{code_value:codes[0].code_value,template_version_id:1,elements_json:doc,data}],rejected:[]};
  else if(p.endsWith('/workstation/print/confirm')){
   if(mode==='failure'){await route.fulfill({status:503,json:{error_code:'UNAVAILABLE',message:'打印结果暂未确认，请先核对实物和设备状态',details:{}}});return;}
   printed=true;body={confirmed:[codes[0].code_value],rejected:[]};
  }
  else if(p.endsWith('/workstation/printer'))body={workstation_id:1,printer_name:'Zenpert 4T200'};
  else if(p.endsWith('/workstation/heartbeat'))body={};
  else throw new Error('未覆盖打印端演示接口 '+p);
  await route.fulfill({json:body});
 });
 async function loginPrint(){await pc.getByPlaceholder('请输入工位操作员账号').fill('demo_operator');await pc.getByPlaceholder('请输入密码',{exact:true}).fill('ExamplePassword');await pc.getByRole('button',{name:'登录',exact:true}).click();}
 await pc.goto('http://127.0.0.1:5174');await capture(pc,'print-login.png');await loginPrint();await pc.getByRole('button',{name:'绑定本机工位',exact:true}).waitFor();await capture(pc,'print-bind.png');
 bound=true;await pc.reload();await loginPrint();await pc.getByText(template.name+' · V1').waitFor();await capture(pc,'print-workspace.png');
 await pc.getByRole('button',{name:'工位状态',exact:true}).click();await pc.getByRole('button',{name:'测试打印一张'}).waitFor();await capture(pc,'print-settings.png');
 await pc.getByRole('button',{name:'打印机驱动安装',exact:true}).click();await capture(pc,'print-drivers.png');
 await pc.getByRole('button',{name:'工位打印',exact:true}).click();await pc.getByRole('button',{name:'开始打印',exact:true}).click();await pc.getByText('已打印',{exact:true}).waitFor();await capture(pc,'print-success.png');
 queue=[{task_id:1,task_type:'reprint',code_value:codes[2].code_value,template_version_id:1,elements_json:doc,data:{...data,code_value:codes[2].code_value},product_name:product.name,company_name:company.name,reason:'标签被撕破，重新打印'}];
 await pc.reload();await loginPrint();await pc.getByRole('button',{name:'标记失败',exact:true}).waitFor();await capture(pc,'print-reprint.png');
 mode='failure';await pc.getByRole('button',{name:'开始打印',exact:true}).click();await pc.getByRole('button',{name:'标记失败并回退'}).waitFor();
 // 失败示例有意展示受控的演示错误，其他截图仍禁止接口错误。
 await pc.locator('#manual-demo-label').evaluate(el=>el.textContent='失败处理示意 · 演示数据');await pc.screenshot({path:path.join(output,'print-failure.png'),animations:'disabled'});console.log('Captured print-failure.png');
 assert.deepEqual(errors,[]);await browser.close();console.log('全部截图生成完成');
})().catch(e=>{console.error(e);process.exit(1)});
