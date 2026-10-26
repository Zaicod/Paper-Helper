import { expect, test } from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs/promises'
test('controlled private PDF preparation, multipart upload, defaults and repaired study on desktop and mobile',async({page})=>{
 const output=path.resolve('.tools/paper-evidence-browser');await fs.mkdir(output,{recursive:true})
 const doc={document_id:'c3e11f49-02c1-4a42-abca-72f7ebfbdb60',status:'missing',message:'未找到公开正文，请上传已有 PDF',filename:'paper.pdf',sha256:'test',source_kind:'uploaded',page_count:2,prepared_at:''}
 const paper={id:2,source:'openalex',paper_id:'W1',title:'MMSTG-Net controlled paper',abstract:'',authors:[],categories:[],page_url:'https://doi.org/10.1/test',note:'',added_at:''}
 const collection={id:7,name:'阅读计划',description:'',paper_count:1,overall_note:'',papers:[paper]}
 const task={task_id:'old',task_type:'study_report',topic:'学习论文',status:'failed',created_at:'2026-10-24T00:00:00Z',updated_at:'2026-10-24T00:00:00Z',events:[],report:null,error_message:'原输入缺少 PDF',error_code:null,sync_error:null}
 let payload:any, upload='',prepare=0,repair:any
 await page.route(url=>url.pathname.startsWith('/api/'),async route=>{
   const request=route.request(),url=new URL(request.url());let data:any
   if(url.pathname==='/api/auth/me')data={id:1,username:'reader',email:'reader@example.test',created_at:''}
   else if(url.pathname==='/api/auth/csrf')data={token:'controlled',header_name:'X-CSRF-TOKEN'}
   else if(url.pathname==='/api/model-settings')data={default_provider:'qwen',providers:[{provider:'qwen',model:'controlled',configured:true,key_hint:'***'}]}
   else if(url.pathname==='/api/library/collections')data={collections:[collection],total:1,page:0,size:100}
   else if(url.pathname==='/api/library/collections/7')data=collection
   else if(url.pathname.endsWith('/document/prepare')){prepare++;data=doc}
   else if(url.pathname.endsWith('/papers/2/document')){
     if(request.method()==='POST'){upload=request.postDataBuffer()!.toString();expect(request.headers()['content-type']).toContain('multipart/form-data; boundary=');expect(request.headers()['x-csrf-token']).toBe('controlled');doc.status='ready'}
     data=doc
   }
   else if(url.pathname==='/api/research/tasks'&&request.method()==='POST'){payload=request.postDataJSON();data={...task,task_id:'old'}}
   else if(url.pathname==='/api/research/tasks/old/repair'){repair=request.postDataJSON();data={...task,task_id:'repaired'}}
   else if(url.pathname.startsWith('/api/research/tasks/'))data={...task,task_id:url.pathname.split('/').pop()}
   else throw Error(`Unexpected boundary ${request.method()} ${url.pathname}`)
   await route.fulfill({json:{code:1,data}})
 })
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message))
 await page.goto('/research/new?task_type=study_report&collection_id=7&paper_ids=2')
 await expect(page.locator('textarea').first()).toHaveValue(/核心创新点/)
 await expect(page.getByRole('button',{name:'生成学习报告',exact:true})).toBeDisabled()
 await page.getByRole('button',{name:'准备论文正文',exact:true}).click();await expect.poll(()=>prepare).toBe(1)
 await page.locator('textarea').first().fill('重点学习模块输入输出')
 await page.getByRole('button',{name:'恢复默认分析要求'}).click()
 await page.locator('input[type="file"]').setInputFiles({name:'controlled.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4 controlled browser fixture')})
 await expect(page.getByRole('button',{name:'生成学习报告',exact:true})).toBeEnabled()
 expect(upload).toContain('name="file"');expect(upload).toContain('%PDF-1.4')
 await page.screenshot({path:path.join(output,'prepared-desktop.png'),fullPage:true})
 await page.setViewportSize({width:390,height:844})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 await page.screenshot({path:path.join(output,'prepared-mobile.png'),fullPage:true})
 await page.getByRole('button',{name:'生成学习报告',exact:true}).click()
 await expect(page).toHaveURL(/\/research\/old$/)
 expect(payload.topic).toContain('核心创新点');expect(payload.paper_ids).toEqual([2])
 await expect(page.getByRole('button',{name:'原输入重试',exact:true})).toBeVisible()
 await page.getByRole('button',{name:'修复资料后重新创建',exact:true}).click()
 await expect(page).toHaveURL(/\/research\/repaired$/)
 expect(repair.idempotency_key).toMatch(/^[0-9a-f-]{36}$/i)
 expect(errors).toEqual([])
})
