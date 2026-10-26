import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import PaperSearchView from '../../src/views/PaperSearchView.vue'
import TaskDetailView from '../../src/views/TaskDetailView.vue'
import ResearchView from '../../src/views/ResearchView.vue'
import { api } from '../../src/api'

const paper = { source: 'openalex', paper_id: 'W1', title: 'SEED-IV EEG and eye movement', abstract: 'Multimodal emotion recognition on SEED-IV', authors: ['Alice'], categories: ['EEG'], page_url: 'https://example.org/paper', pdf_url: 'javascript:alert(1)', cited_by_count: 3 }
const report = {
  report_type: 'search_report', topic: '多模态情绪识别 seediv seedvii', generated_at: '2026-10-24T00:00:00Z', rounds: 2,
  plan: { summary: '跨来源检索情绪识别', concepts: ['multimodal emotion recognition'], entities: [{ name: 'SEED-IV', aliases: ['seediv'] }, { name: 'SEED-VII', aliases: ['seedvii'] }], entity_relation: 'any', constraints: ['EEG 与眼动'], queries: [{ source: 'openalex', keywords: [{ text: 'SEED-IV', match_mode: 'fuzzy' }], purpose: '查找指定数据集' }] },
  results: [{ candidate_id: 'c1', paper, relevance: 'match', reason: '摘要包含目标数据集与模态', evidence: ['Multimodal emotion recognition on SEED-IV'], matched_entities: ['SEED-IV'], modality: 'multimodal', provenance: [{ source: 'openalex', query: 'SEED-IV multimodal' }] }],
  searches: [{ round: 1, source: 'openalex', query: 'SEED-IV multimodal', count: 1, status: 'ok' }, { round: 2, source: 'arxiv', query: 'SEED-VII', count: 0, status: 'rate_limited' }], warnings: ['arXiv 暂时限流'], gaps: ['SEED-VII 证据不足'],
}
const task = { task_id: 'search-1', task_type: 'search', topic: report.topic, status: 'completed', created_at: '', updated_at: '', events: [], report, error_code: null, error_message: null, sync_error: null }
beforeEach(() => {
  localStorage.clear()
  vi.spyOn(api.collections, 'list').mockResolvedValue({ collections: [{ id: 7, name: '情绪识别', description: '', paper_count: 0 }], total: 1, page: 0, size: 100 })
})
afterEach(() => vi.restoreAllMocks())
async function page(component: any, path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/papers', component: PaperSearchView }, { path: '/research', component: ResearchView }, { path: '/research/:id', component: TaskDetailView }, { path: '/settings', component: { template: '<div />' } }, { path: '/collections', component: { template: '<div />' } }, { path: '/research/new', component: { template: '<div />' } }] })
  await router.push(path)
  const wrapper = mount(component, { global: { plugins: [router, createPinia()] } })
  await flushPromises()
  return { wrapper, router }
}
it('submits a default-model live search, retains the key after ambiguous failure and navigates asynchronously', async () => {
  const create = vi.spyOn(api.tasks, 'create').mockRejectedValueOnce(new Error('响应超时')).mockResolvedValueOnce({ ...task, report: null, status: 'queued' } as any)
  vi.spyOn(api.tasks, 'get').mockResolvedValue(task as any)
  const { wrapper, router } = await page(PaperSearchView, '/papers')
  expect(wrapper.find('a[href="/settings"]').exists()).toBe(true)
  expect(wrapper.text()).toContain('默认模型')
  await wrapper.get('#intelligent-topic').setValue(report.topic)
  await wrapper.get('[data-test="intelligent-search-form"]').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('响应超时')
  const first = create.mock.calls[0]![0]
  expect(first).toEqual({ topic: report.topic, mode: 'live', rag: 'none', limit: 10, task_type: 'search', idempotency_key: expect.any(String) })
  await wrapper.get('[data-test="intelligent-search-form"]').trigger('submit')
  await flushPromises()
  expect(create.mock.calls[1]![0]).toEqual(first)
  expect(router.currentRoute.value.path).toBe('/research/search-1')
  wrapper.unmount()
})
it('uses a new idempotency key after changing the search topic', async () => {
  const create = vi.spyOn(api.tasks, 'create').mockRejectedValue(new Error('离线'))
  const { wrapper } = await page(PaperSearchView, '/papers')
  await wrapper.get('#intelligent-topic').setValue('seediv')
  await wrapper.get('[data-test="intelligent-search-form"]').trigger('submit'); await flushPromises()
  await wrapper.get('#intelligent-topic').setValue('seedvii')
  await wrapper.get('[data-test="intelligent-search-form"]').trigger('submit'); await flushPromises()
  expect(create.mock.calls[0]![0].idempotency_key).not.toBe(create.mock.calls[1]![0].idempotency_key)
  wrapper.unmount()
})
it('renders search reports separately with evidence, provenance, limitations and safe collection saving', async () => {
  vi.spyOn(api.tasks, 'get').mockResolvedValue(task as any)
  const save = vi.spyOn(api.collections, 'addPaper').mockResolvedValue({ ...paper, id: 1, added_at: '', note: '' })
  const { wrapper } = await page(TaskDetailView, '/research/search-1')
  for (const text of ['智能搜索', 'multimodal emotion recognition', 'SEED-IV', 'seediv', '满足任一实体', '查找指定数据集', '第 2 轮', '限流', paper.title, report.results[0]!.reason, report.results[0]!.evidence[0]!, 'SEED-VII 证据不足', '元数据相关性', '多模态', 'SEED-IV multimodal']) expect(wrapper.text()).toContain(text)
  expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false)
  expect(wrapper.get('a[href="https://example.org/paper"]').attributes('rel')).toBe('noopener noreferrer')
  await wrapper.get('#search-report-collection').setValue('7')
  await wrapper.get('[data-test="save-search-result"]').trigger('click'); await flushPromises()
  expect(save).toHaveBeenCalledWith(7, paper)
  expect(wrapper.get('[data-test="save-search-result"]').attributes('disabled')).toBeDefined()
  wrapper.unmount()
})
it('accepts a valid search report with no results and explains remaining gaps', async () => {
  vi.spyOn(api.tasks, 'get').mockResolvedValue({ ...task, report: { ...report, results: [] } } as any)
  const { wrapper } = await page(TaskDetailView, '/research/search-1')
  expect(wrapper.text()).toContain('没有找到可返回的论文')
  expect(wrapper.text()).toContain('SEED-VII 证据不足')
  wrapper.unmount()
})
it('labels search tasks correctly in the task list', async () => {
  vi.spyOn(api.tasks, 'list').mockResolvedValue({ tasks: [task], total: 1, page: 0, size: 10 } as any)
  const { wrapper } = await page(ResearchView, '/research')
  expect(wrapper.get('.task-row').text()).toContain('智能搜索')
  wrapper.unmount()
})
it('identifies a search task while it is still queued without a report', async () => {
  vi.spyOn(api.tasks, 'get').mockResolvedValue({ ...task, status: 'queued', report: null } as any)
  const { wrapper } = await page(TaskDetailView, '/research/search-1')
  expect(wrapper.get('.page-heading').text()).toContain('智能搜索')
  wrapper.unmount()
})
