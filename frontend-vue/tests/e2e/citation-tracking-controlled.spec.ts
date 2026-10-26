import {expect,test} from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs/promises'
test('controlled citation discovery entry, direction, provenance and collection saving on desktop/mobile',async({page})=>{
 const output=path.resolve('.tools/citation-browser');await fs.mkdir(output,{recursive:true})
 const paper={id:2,source:'openalex',paper_id:'W1',title:'SEED-IV multimodal emotion seed',abstract:'EEG and eye tracking',authors:['Alice'],categories:[],page_url:'https://example.org/seed',note:'',added_at:''}
 const result={...paper,id:3,paper_id:'W2',title:'Cross-modal alignment for SEED-IV',pdf_url:'javascript:alert(1)'}
 const collection={id:7,name:'多模态情绪识别',description:'',overall_note:'',paper_count:1,papers:[paper]}
 const report={report_type:'citation_report',topic:'情绪识别',generated_at:'2026-10-26T00:00:00Z',direction:'both',seeds:[paper],depth:1,source_requests:3,results:[{candidate_id:'c1',paper:result,relevance:'match',reason:'标题与摘要提及目标数据集和模态',evidence:['EEG and eye tracking'],paths:[{seed_id:'W1',seed_title:paper.title,direction:'references',from_id:'W1',to_id:'W2'},{seed_id:'W1',seed_title:paper.title,direction:'citations',from_id:'W2',to_id:'W1'}]}],warnings:['受控来源，未调用真实检索'],gaps:['需要阅读全文核对实验设置']}
 const task={task_id:'citation-1',task_type:'citation_trace',topic:'情绪识别',status:'completed',created_at:'2026-10-26T00:00:00Z',updated_at:'2026-10-26T00:00:00Z',events:[],report,error_code:null,error_message:null,sync_error:null}
 let payload:any,saved:any,documentReads=0
 await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url());if(!url.pathname.startsWith('/api/'))return route.continue();let data:any
  if(url.pathname==='/api/auth/me')data={id:1,username:'learner',email:'test@example.org',created_at:''}
  else if(url.pathname==='/api/auth/csrf')data={token:'controlled',header_name:'X-CSRF-TOKEN'}
  else if(url.pathname==='/api/model-settings')data={default_provider:'qwen',providers:[{provider:'qwen',model:'qwen-plus',configured:true,key_hint:'***'}]}
  else if(url.pathname==='/api/library/collections')data={collections:[collection],total:1,page:0,size:100}
  else if(url.pathname==='/api/library/collections/7')data=collection
  else if(url.pathname.endsWith('/document')){documentReads++;data={document_id:null,status:'missing',message:'正文未准备',filename:null,sha256:null,source_kind:null,page_count:null,prepared_at:null}}
  else if(url.pathname==='/api/research/tasks'&&request.method()==='POST'){payload=request.postDataJSON();expect(request.headers()['x-csrf-token']).toBe('controlled');data=task}
  else if(url.pathname==='/api/research/tasks/citation-1')data=task
  else if(url.pathname==='/api/library/collections/7/papers'&&request.method()==='POST'){saved=request.postDataJSON();data={...result,id:3}}
  else throw Error(`Unexpected boundary ${request.method()} ${url.pathname}`)
  await route.fulfill({json:{code:1,data}})
 })
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message))
 await page.goto('/collections/7')
 await page.getByRole('checkbox',{name:/选择学习报告论文/}).check()
 await page.locator('[data-test=trace-selected-citations]').click()
 await expect(page).toHaveURL(/task_type=citation_trace/)
 const priorDocumentReads=documentReads
 await expect(page.locator('textarea').first()).toHaveValue(/追踪相关参考文献/)
 await expect(page.locator('[data-test=citation-direction]')).toHaveValue('both')
 await page.locator('[data-test=citation-direction]').selectOption('references')
 await page.locator('[data-test=citation-direction]').selectOption('both')
 await page.locator('input[type="number"]').fill('12')
 await page.getByRole('button',{name:'开始引用追踪',exact:true}).click()
 await expect(page).toHaveURL(/\/research\/citation-1$/)
 expect(payload).toMatchObject({task_type:'citation_trace',citation_direction:'both',paper_ids:[2],limit:12,mode:'live',rag:'none'})
 expect(payload.provider).toBeUndefined();expect(payload.model).toBeUndefined();expect(documentReads).toBe(priorDocumentReads)
 await expect(page.getByRole('heading',{name:result.title,exact:true})).toBeVisible()
 await expect(page.getByText('后续研究：这篇论文引用了种子论文')).toBeVisible()
 expect(await page.locator('a[href^="javascript:"]').count()).toBe(0)
 await page.locator('#citation-report-collection').selectOption('7')
 await page.locator('[data-test=save-citation-result]').click()
 await expect(page.locator('[data-test=save-citation-result]')).toHaveText('已加入此收藏夹')
 expect(saved.paper_id).toBe('W2')
 await page.screenshot({path:path.join(output,'citation-desktop.png'),fullPage:true})
 await page.setViewportSize({width:390,height:844})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 await page.screenshot({path:path.join(output,'citation-mobile.png'),fullPage:true})
 expect(errors).toEqual([])
})
