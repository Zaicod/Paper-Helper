import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSubmission } from '../../src/composables/submission'
import { createTaskPoller } from '../../src/composables/polling'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ReportView from '../../src/components/ReportView.vue'
import ResearchNewView from '../../src/views/ResearchNewView.vue'
import { api } from '../../src/api'
import type { Report } from '../../src/types'

afterEach(() => { vi.useRealTimers() })

describe('research submission intent', () => {
  it('preserves the execution key on uncertain retries and changes it for edited content', () => {
    let number = 0
    const submission = createSubmission(() => `key-${++number}`)
    const first = submission.keyFor({ topic: 'RAG', mode: 'demo' })
    expect(submission.keyFor({ topic: 'RAG', mode: 'demo' })).toBe(first)
    expect(submission.keyFor({ topic: 'Edited', mode: 'demo' })).not.toBe(first)
    submission.reset()
    expect(submission.keyFor({ topic: 'RAG', mode: 'demo' })).toBe('key-3')
  })
})

describe('task polling lifecycle', () => {
  it('waits until each request finishes and stops on a terminal response', async () => {
    vi.useFakeTimers()
    let finish!: (value: { status: string }) => void
    const request = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
      .mockResolvedValue({ status: 'completed' })
    const result = vi.fn()
    const poller = createTaskPoller(request, result, vi.fn())
    poller.start('a')
    await vi.advanceTimersByTimeAsync(5000)
    expect(request).toHaveBeenCalledTimes(1)
    finish({ status: 'running' })
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(1500)
    expect(request).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(5000)
    expect(request).toHaveBeenCalledTimes(2)
    poller.stop()
  })

  it('ignores old route results and stops timers when the view leaves', async () => {
    vi.useFakeTimers()
    let finishOld!: (value: { status: string; id: string }) => void
    const request = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
      .mockResolvedValue({ status: 'running', id: 'new' })
    const result = vi.fn()
    const poller = createTaskPoller(request, result, vi.fn())
    poller.start('old')
    poller.start('new')
    await vi.advanceTimersByTimeAsync(0)
    finishOld({ status: 'completed', id: 'old' })
    await vi.advanceTimersByTimeAsync(0)
    expect(result).toHaveBeenCalledTimes(1)
    expect(result).toHaveBeenCalledWith({ status: 'running', id: 'new' })
    poller.stop()
    await vi.advanceTimersByTimeAsync(5000)
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('stops after communication errors and exposes an explicit retry', async () => {
    vi.useFakeTimers()
    const request = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ status: 'completed' })
    const error = vi.fn()
    const poller = createTaskPoller(request, vi.fn(), error)
    poller.start('a')
    await vi.advanceTimersByTimeAsync(5000)
    expect(error).toHaveBeenCalledTimes(1)
    expect(request).toHaveBeenCalledTimes(1)
    poller.start('a')
    await vi.advanceTimersByTimeAsync(0)
    expect(request).toHaveBeenCalledTimes(2)
    poller.stop()
  })
})

describe('research pages', () => {
  it('uses the same key after a failed create and a new key when the form changes', async () => {
    vi.spyOn(api.collections, 'list').mockResolvedValue({ collections: [], total: 0, page: 0, size: 100 })
    const create = vi.spyOn(api.tasks, 'create').mockRejectedValue(new Error('连接中断'))
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/research/new', component: ResearchNewView },
      { path: '/research/:id', component: { template: '<div>task</div>' } },
      { path: '/research', component: { template: '<div>list</div>' } },
    ] })
    await router.push('/research/new')
    const wrapper = mount(ResearchNewView, { global: { plugins: [router] } })
    await flushPromises()
    await wrapper.get('textarea').setValue('检索增强生成')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(create).toHaveBeenCalledTimes(2)
    expect(create.mock.calls[0]![0].idempotency_key).toBe(create.mock.calls[1]![0].idempotency_key)
    expect(create.mock.calls[0]![0].mode).toBe('demo')
    expect(wrapper.text()).toContain('演示研究团队')
    await wrapper.get('textarea').setValue('  检索增强生成  ')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(create.mock.calls[2]![0].topic).toBe('检索增强生成')
    expect(create.mock.calls[2]![0].idempotency_key).toBe(create.mock.calls[0]![0].idempotency_key)
    await wrapper.get('textarea').setValue('新的主题')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(create.mock.calls[3]![0].idempotency_key).not.toBe(create.mock.calls[0]![0].idempotency_key)
    wrapper.unmount()
  })

  it('renders report text safely, all evidence sections, and only http(s) source links', () => {
    const report: Report = {
      topic: '<img src=x onerror=alert(1)>', generated_at: '2026-10-19T00:00:00Z',
      papers: [{ paper_id: 'p1', source: 'manual', title: '论文', authors: ['作者'], abstract: '摘要', categories: [], page_url: 'javascript:alert(1)', pdf_url: 'https://example.com/paper.pdf' }],
      analyses: [{ paper_id: 'p1', title: '分析标题', research_problem: '研究问题', innovation_points: ['创新'], methods: ['方法'], results: ['结果'], limitations: ['局限'], evidence_notes: ['证据说明'], datasets: ['数据集'], citations: ['chunk-1'] }],
      synthesis: { topic: '主题', overview: '综合概览', method_taxonomy: ['方法分类'], common_findings: ['共同发现'], disagreements: ['差异'], research_gaps: ['空白'], evidence_map: ['对应证据'] },
      idea_portfolio: { topic: '主题', caution: '构思须验证', ideas: [{ title: '构思标题', target_gap: '空白', hypothesis: '假设', proposed_method: ['实施步骤'], expected_contribution: '贡献', evaluation_plan: ['评估'], risks: ['风险'], related_paper_ids: ['p1'] }] },
      analysis_failures: [{ paper_id: 'p2', stage: 'analysis', error_type: 'timeout', retry_count: 2, message: '未完成的分析' }],
      context_audits: [{ paper_id: 'p1', query: '检索问题', selected_chunk_ids: ['chunk-1'], dropped_count: 1, estimated_tokens: 20, token_budget: 6000, source_mode: 'abstract', decisions: [{ action: 'analyze', confidence: 0.9, source: 'fixture' }] }],
    }
    const wrapper = mount(ReportView, { props: { report } })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain(report.topic)
    expect(wrapper.findAll('a')).toHaveLength(1)
    expect(wrapper.get('a').attributes('href')).toBe('https://example.com/paper.pdf')
    expect(wrapper.get('a').attributes('rel')).toBe('noopener noreferrer')
    for (const text of ['创新', '局限', '数据集', '构思标题', '检索问题', 'chunk-1', '未完成的分析']) expect(wrapper.text()).toContain(text)
    wrapper.unmount()
  })
})
