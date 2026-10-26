import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperDocumentControl from '../../src/components/PaperDocumentControl.vue'
import { api } from '../../src/api'
import { createPinia } from 'pinia'
const paper = {id:2,source:'openalex',paper_id:'W1',title:'paper',abstract:'',authors:[],categories:[],page_url:'https://doi.org/x',note:'',added_at:''}
const ready = {document_id:'c3e11f49-02c1-4a42-abca-72f7ebfbdb60',status:'ready' as const,message:'已准备',filename:'paper.pdf',sha256:'hash',source_kind:'uploaded' as const,page_count:2,prepared_at:''}
afterEach(()=>vi.restoreAllMocks())
it('uploads the selected PDF and displays private authenticated download',async()=>{
  vi.spyOn(api.documents,'get').mockResolvedValue({...ready,status:'missing',document_id:null})
  const upload=vi.spyOn(api.documents,'upload').mockResolvedValue(ready)
  const wrapper=mount(PaperDocumentControl,{props:{collectionId:7,paper}});await flushPromises()
  const file=new File(['%PDF-test'],'paper.pdf',{type:'application/pdf'})
  Object.defineProperty(wrapper.get('input[type="file"]').element,'files',{value:[file],configurable:true})
  await wrapper.get('input[type="file"]').trigger('change');await flushPromises()
  expect(upload).toHaveBeenCalledWith(7,2,file)
  expect(wrapper.get('a').attributes('href')).toBe(`/api/library/documents/${ready.document_id}/file`)
  expect(wrapper.text()).toContain('本人上传')
  wrapper.unmount()
})
it('does not allow an old paper preparation response to overwrite the new paper status',async()=>{
  vi.spyOn(api.documents,'get').mockResolvedValue({...ready,status:'missing',document_id:null})
  let finish!:(value:typeof ready)=>void
  vi.spyOn(api.documents,'prepare').mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const wrapper=mount(PaperDocumentControl,{props:{collectionId:7,paper}});await flushPromises()
  await wrapper.get('[data-test="prepare-document"]').trigger('click')
  await wrapper.setProps({paper:{...paper,id:3}});await flushPromises()
  finish(ready);await flushPromises()
  expect(wrapper.text()).toContain('缺少正文')
  expect(wrapper.find('a').exists()).toBe(false)
  wrapper.unmount()
})
it('shows an explicit status error and never treats failed lookup as prepared',async()=>{
  vi.spyOn(api.documents,'get').mockRejectedValue(new Error('正文状态暂不可用'))
  const wrapper=mount(PaperDocumentControl,{props:{collectionId:7,paper}});await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('正文状态暂不可用')
  expect(wrapper.emitted('status')?.flat()).toEqual([null])
  expect(wrapper.find('a').exists()).toBe(false)
  wrapper.unmount()
})
it('rejects an empty or oversized upload before transport',async()=>{
  vi.spyOn(api.documents,'get').mockResolvedValue({...ready,status:'missing'})
  const upload=vi.spyOn(api.documents,'upload')
  const wrapper=mount(PaperDocumentControl,{props:{collectionId:7,paper}});await flushPromises()
  const file=new File([],'empty.pdf',{type:'application/pdf'})
  Object.defineProperty(wrapper.get('input[type="file"]').element,'files',{value:[file],configurable:true})
  await wrapper.get('input[type="file"]').trigger('change')
  expect(upload).not.toHaveBeenCalled()
  expect(wrapper.get('[role="alert"]').text()).toContain('非空')
  wrapper.unmount()
})

it('ignores preparation from a previous signed-in account',async()=>{
  const pinia=createPinia();pinia.state.value.auth={user:{id:1}}
  vi.spyOn(api.documents,'get').mockResolvedValue({...ready,status:'missing',document_id:null})
  let finish!:(value:typeof ready)=>void
  vi.spyOn(api.documents,'prepare').mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const wrapper=mount(PaperDocumentControl,{props:{collectionId:7,paper},global:{plugins:[pinia]}});await flushPromises()
  await wrapper.get('[data-test="prepare-document"]').trigger('click')
  pinia.state.value.auth={user:{id:2}};await flushPromises()
  finish(ready);await flushPromises()
  expect(wrapper.find('a').exists()).toBe(false)
  expect(wrapper.text()).toContain('缺少正文')
  wrapper.unmount()
})
