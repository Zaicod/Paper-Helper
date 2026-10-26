import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ResearchNewView from '../../src/views/ResearchNewView.vue'
import { api } from '../../src/api'
const paper = {id:2,source:'openalex',paper_id:'W1',title:'MMSTG',abstract:'',authors:[],categories:[],page_url:'https://doi.org/10.1/x',note:'',added_at:''}
const document = {document_id:null,status:'missing' as const,message:'未找到正文，请上传 PDF',filename:null,sha256:null,source_kind:null,page_count:null,prepared_at:null}
afterEach(() => vi.restoreAllMocks())
async function form(path='/research/new?task_type=study_report&collection_id=7') {
  vi.spyOn(api.modelSettings,'get').mockRejectedValue(new Error('offline'))
  vi.spyOn(api.collections,'list').mockResolvedValue({collections:[{id:7,name:'阅读',description:'',paper_count:1}],total:1,page:0,size:100})
  vi.spyOn(api.collections,'get').mockResolvedValue({id:7,name:'阅读',description:'',overall_note:'',paper_count:1,papers:[paper]})
  vi.spyOn(api.documents,'get').mockResolvedValue(document)
  const router = createRouter({history:createMemoryHistory(),routes:[{path:'/research/new',component:ResearchNewView},{path:'/research',component:{template:'<div />'}},{path:'/settings',component:{template:'<div />'}}]})
  await router.push(path)
  const wrapper=mount(ResearchNewView,{global:{plugins:[router]}}); await flushPromises();return wrapper
}
it('defaults selected-paper analysis and blocks study until PDF is prepared',async()=>{
  const create=vi.spyOn(api.tasks,'create').mockRejectedValue(new Error('offline'))
  const prepare=vi.spyOn(api.documents,'prepare').mockResolvedValue({...document,status:'ready',document_id:'c3e11f49-02c1-4a42-abca-72f7ebfbdb60'})
  const wrapper=await form()
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toContain('核心创新点')
  expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  await wrapper.get('form').trigger('submit'); expect(create).not.toHaveBeenCalled()
  await wrapper.get('[data-test="prepare-document"]').trigger('click');await flushPromises()
  expect(prepare).toHaveBeenCalledWith(7,2)
  expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  await wrapper.get('form').trigger('submit');await flushPromises(); expect(create).toHaveBeenCalledOnce()
  wrapper.unmount()
})
it('preserves manual topic when selections change and restores the default explicitly',async()=>{
  const wrapper=await form()
  await wrapper.get('textarea').setValue('我要分析消融')
  await wrapper.get('input[type="checkbox"]').setValue(false)
  await wrapper.get('input[type="checkbox"]').setValue(true)
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('我要分析消融')
  await wrapper.get('[data-test="restore-default-topic"]').trigger('click')
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toContain('核心创新点')
  wrapper.unmount()
})
it('never prefills the generic analysis instruction for topic-only search',async()=>{
  const wrapper=await form('/research/new')
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
  wrapper.unmount()
})
