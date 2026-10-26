import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ResearchNewView from '../../src/views/ResearchNewView.vue'
import TaskDetailView from '../../src/views/TaskDetailView.vue'
import { api } from '../../src/api'

const seed = { id:2, source:'openalex',paper_id:'W1',title:'Seed paper',abstract:'SEED-IV EEG',authors:[],categories:[],page_url:'https://example.org/seed',note:'',added_at:'' }
const candidate = {source:'openalex',paper_id:'W2',title:'SEED-IV follow-up',abstract:'EEG and eye tracking',authors:['Alice'],categories:[],page_url:'https://example.org/followup',pdf_url:'javascript:alert(1)'}
const report = {report_type:'citation_report',topic:'情绪识别',generated_at:'2026-10-26T00:00:00Z',direction:'both',depth:1,source_requests:3,seeds:[seed],results:[{candidate_id:'c1',paper:candidate,relevance:'match',reason:'元数据提及 EEG',evidence:['EEG and eye tracking'],paths:[{seed_id:'W1',seed_title:seed.title,direction:'references',from_id:'W1',to_id:'W2'},{seed_id:'W1',seed_title:seed.title,direction:'citations',from_id:'W2',to_id:'W1'}]}],warnings:['结果范围受限'],gaps:['需要核查全文']}
afterEach(()=>vi.restoreAllMocks())
async function page(component:any,path:string,count=1){
 vi.spyOn(api.modelSettings,'get').mockResolvedValue({default_provider:'qwen',providers:[{provider:'qwen',model:'qwen-plus',configured:true,key_hint:'***'}]} as any)
 vi.spyOn(api.collections,'list').mockResolvedValue({collections:[{id:7,name:'研究',description:'',paper_count:count}],total:1,page:0,size:100})
 vi.spyOn(api.collections,'get').mockResolvedValue({id:7,name:'研究',description:'',overall_note:'',paper_count:count,papers:Array.from({length:count},(_,i)=>({...seed,id:i+2,paper_id:'W'+(i+1)}))})
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/research/new',component:ResearchNewView},{path:'/research/:id',component:TaskDetailView},{path:'/research',component:{template:'<div />'}},{path:'/settings',component:{template:'<div />'}},{path:'/collections',component:{template:'<div />'}}]})
 await router.push(path)
 const wrapper=mount(component,{global:{plugins:[router,createPinia()]}});await flushPromises();return {wrapper,router}
}
it('submits selected seeds with citation default, direction and independent result limit without PDF preparation',async()=>{
 const create=vi.spyOn(api.tasks,'create').mockRejectedValue(new Error('offline'))
 const document=vi.spyOn(api.documents,'get')
 const {wrapper}=await page(ResearchNewView,'/research/new?task_type=citation_trace&collection_id=7&paper_ids=2')
 expect(wrapper.text()).toContain('引用追踪')
 expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toContain('追踪相关参考文献及后续研究')
 expect(wrapper.find('[data-test="task-provider"]').exists()).toBe(false)
 await wrapper.get('[data-test="citation-direction"]').setValue('citations')
 await wrapper.get('input[type="number"]').setValue(12)
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(create).toHaveBeenCalledWith(expect.objectContaining({task_type:'citation_trace',citation_direction:'citations',mode:'live',rag:'none',collection_id:7,paper_ids:[2],limit:12}))
 expect(create.mock.calls[0]![0]).not.toHaveProperty('provider')
 expect(create.mock.calls[0]![0]).not.toHaveProperty('model')
 expect(document).not.toHaveBeenCalled()
 wrapper.unmount()
})
it('limits citation seed selection to five and blocks empty selection',async()=>{
 const create=vi.spyOn(api.tasks,'create').mockRejectedValue(new Error('offline'))
 const {wrapper}=await page(ResearchNewView,'/research/new?task_type=citation_trace&collection_id=7',6)
 const boxes=wrapper.findAll('input[type="checkbox"]')
 expect(boxes.filter(x=>(x.element as HTMLInputElement).checked)).toHaveLength(5)
 expect(boxes[5]!.attributes('disabled')).toBeDefined()
 for(const box of boxes.slice(0,5))await box.setValue(false)
 await wrapper.get('form').trigger('submit');await flushPromises()
 expect(create).not.toHaveBeenCalled()
 expect(wrapper.text()).toContain('1 至 5')
 wrapper.unmount()
})
it('renders both path directions, limitations and safe collection saving in task details',async()=>{
 vi.spyOn(api.tasks,'get').mockResolvedValue({task_id:'citation-1',task_type:'citation_trace',topic:'情绪识别',status:'completed',events:[],report,created_at:'',updated_at:'',error_code:null,error_message:null,sync_error:null} as any)
 const save=vi.spyOn(api.collections,'addPaper').mockResolvedValue({...candidate,id:9,note:'',added_at:''})
 const {wrapper}=await page(TaskDetailView,'/research/citation-1')
 for(const text of ['引用追踪','Seed paper','SEED-IV follow-up','参考文献','引用了种子论文','EEG and eye tracking','结果范围受限','需要核查全文','不代表支持'])expect(wrapper.text()).toContain(text)
 expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false)
 await wrapper.get('#citation-report-collection').setValue('7')
 await wrapper.get('[data-test="save-citation-result"]').trigger('click');await flushPromises()
 expect(save).toHaveBeenCalledWith(7,candidate)
 wrapper.unmount()
})

it('ignores a delayed create response after the user leaves the original form route',async()=>{
 let finish!:(value:any)=>void
 vi.spyOn(api.tasks,'create').mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
 const {wrapper,router}=await page(ResearchNewView,'/research/new?task_type=citation_trace&collection_id=7')
 await wrapper.get('form').trigger('submit');await flushPromises()
 await router.push('/research/new?task_type=citation_trace&collection_id=8')
 finish({task_id:'late'});await flushPromises()
 expect(router.currentRoute.value.query.collection_id).toBe('8')
 wrapper.unmount()
})
