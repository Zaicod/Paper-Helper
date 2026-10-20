import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ResearchNewView from '../../src/views/ResearchNewView.vue'
import { api } from '../../src/api'
import StudyReportView from '../../src/components/StudyReportView.vue'
import CollectionDetailView from '../../src/views/CollectionDetailView.vue'
import type { StudyReport } from '../../src/types'

afterEach(() => vi.restoreAllMocks())

it('creates a live study report using only the papers selected from the collection link', async () => {
  const paper = (id: number) => ({ id, source: 'arxiv', paper_id: `p${id}`, title: `论文 ${id}`, abstract: '摘要', authors: [], categories: [], page_url: 'https://arxiv.org/abs/1234.12345', note: '', added_at: '' })
  vi.spyOn(api.collections, 'list').mockResolvedValue({ collections: [{ id: 7, name: '阅读计划', description: '', paper_count: 2 }], total: 1, page: 0, size: 100 })
  vi.spyOn(api.collections, 'get').mockResolvedValue({ id: 7, name: '阅读计划', description: '', overall_note: '', paper_count: 2, papers: [paper(1), paper(2)] })
  const create = vi.spyOn(api.tasks, 'create').mockRejectedValue(new Error('暂时离线'))
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/research/new', component: ResearchNewView }, { path: '/research', component: { template: '<div />' } }] })
  await router.push('/research/new?task_type=study_report&collection_id=7&paper_ids=2')
  const wrapper = mount(ResearchNewView, { global: { plugins: [router] } })
  await flushPromises()
  expect(wrapper.text()).toContain('学习报告')
  expect(wrapper.text()).toContain('开放获取 PDF')
  await wrapper.get('textarea').setValue('多模态方法学习')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(create).toHaveBeenCalledWith(expect.objectContaining({ task_type: 'study_report', mode: 'live', collection_id: 7, paper_ids: [2] }))
  wrapper.unmount()
})

it('renders the four learning sections, safe page evidence, and a task-scoped DOCX download', () => {
  const report: StudyReport = {
    report_type: 'study_report', topic: '学习报告', generated_at: '2026-10-19T00:00:00Z', papers: [], mode: 'live', evidence_mode: 'pdf',
    analyses: [{ paper_id: 'p1', title: '<img src=x onerror=alert(1)>', overview: '概述', background: '背景问题', methods: [{ name: '融合模块', purpose: '跨模态交互', inputs: '文本与视觉', outputs: '融合表征' }], innovations: ['创新'], results: ['实验指标'], reflection: ['学习建议'], citations: [{ chunk_id: 'chunk-1', page_number: 3, source_url: 'https://arxiv.org/pdf/1234.12345' }, { chunk_id: 'chunk-2', page_number: null, source_url: 'javascript:alert(1)' }] }], synthesis: ['对比总结'], learning_plan: ['复现模块'],
  }
  const wrapper = mount(StudyReportView, { props: { report, taskId: 'task-123' } })
  for (const text of ['论文概述', '1. 研究背景与问题', '2. 模型方法（模块解释）', '3. 创新点 & 实验结果', '4. 学习体会', '融合模块', '文本与视觉', '融合表征', '第 3 页', '对比总结', '复现模块']) expect(wrapper.text()).toContain(text)
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.findAll('a')).toHaveLength(2)
  expect(wrapper.get('a[download]').attributes('href')).toBe('/api/research/tasks/task-123/document')
  expect(wrapper.get('a[target="_blank"]').attributes('rel')).toBe('noopener noreferrer')
  wrapper.unmount()
})

it('selects at most twenty collection papers and clears the study selection', async () => {
  const papers = Array.from({ length: 21 }, (_, index) => ({ id: index + 1, source: 'arxiv', paper_id: `p${index}`, title: `论文${index}`, abstract: '', authors: [], categories: [], page_url: 'https://arxiv.org/abs/1234.12345', added_at: '', note: '' }))
  vi.spyOn(api.collections, 'get').mockResolvedValue({ id: 7, name: '阅读计划', description: '', overall_note: '', paper_count: 21, papers })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/collections/:id', component: CollectionDetailView }, { path: '/collections', component: { template: '<div />' } }, { path: '/research/new', component: { template: '<div />' } }] })
  await router.push('/collections/7')
  const wrapper = mount(CollectionDetailView, { global: { plugins: [router] } })
  await flushPromises()
  await wrapper.get('[data-test="select-study-papers"]').trigger('click')
  expect(wrapper.findAll('input[type="checkbox"]:checked')).toHaveLength(20)
  const link = wrapper.findAll('a').find(item => item.text() === '生成所选论文学习报告')!
  expect(link.attributes('href')).toContain('task_type=study_report')
  expect(link.attributes('href')).toContain('collection_id=7')
  expect(wrapper.findAll('input[type="checkbox"]')[20]!.attributes('disabled')).toBeDefined()
  await wrapper.get('[data-test="clear-study-papers"]').trigger('click')
  expect(wrapper.findAll('input[type="checkbox"]:checked')).toHaveLength(0)
  wrapper.unmount()
})
