import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import TaskDetailView from '../../src/views/TaskDetailView.vue'
import { api } from '../../src/api'
import type { Task, TaskStatus } from '../../src/types'

const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks() })
function task(status: TaskStatus = 'failed', id = 'old'): Task {
  return { task_id: id, topic: '学习主题', status, task_type: 'study_report', created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z', events: [], report: null, error_code: null, error_message: status === 'failed' ? '原任务错误' : null, sync_error: null }
}
async function setup(status: TaskStatus = 'failed') {
  vi.spyOn(api.tasks, 'get').mockImplementation(async id => task(status, id))
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/research/:id', component: TaskDetailView },
    { path: '/research', component: { template: '<div>list</div>' } },
    { path: '/settings', component: { template: '<div>settings</div>' } },
  ] })
  await router.push('/research/old')
  const wrapper = mount(TaskDetailView, { global: { plugins: [router] } })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}

describe('retrying failed task records', () => {
  it('returns to the originating history search and page', async () => {
    const { wrapper, router } = await setup()
    await router.push('/research/old?category=history&keyword=Agent&page=2')
    await flushPromises()
    const back = wrapper.findAll('a').find(link => link.text() === '返回任务')!
    expect(back.attributes('href')).toBe('/research?category=history&keyword=Agent&page=2')
  })
  it.each(['failed', 'interrupted'] as const)('offers retry and current configuration guidance for %s', async status => {
    const { wrapper } = await setup(status)
    expect(wrapper.get('[data-test="retry-task"]').text()).toBe('重试任务')
    expect(wrapper.text()).toContain('当前')
    expect(wrapper.text()).toContain('新任务记录')
    expect(wrapper.text()).toContain('原任务记录会保留')
    expect(wrapper.text()).toContain('本次执行未产生阶段记录，可修正配置后重试。')
    expect(wrapper.text()).not.toContain('等待执行端返回阶段记录')
    expect(wrapper.get('a[href="/settings"]').text()).toContain('个人设置')
    expect(wrapper.get('a[href="/research/new"]').text()).toBe('创建新的研究任务')
  })

  it.each(['queued', 'running', 'completed'] as const)('does not retry a %s task', async status => {
    const { wrapper } = await setup(status)
    expect(wrapper.find('[data-test="retry-task"]').exists()).toBe(false)
  })

  it('submits one pending intent and navigates to the returned new record', async () => {
    const { wrapper, router } = await setup()
    let finish!: (value: Task) => void
    const retry = vi.spyOn(api.tasks, 'retry').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('[data-test="retry-task"]').trigger('click')
    expect(wrapper.get('[data-test="retry-task"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="retry-task"]').trigger('click')
    expect(retry).toHaveBeenCalledTimes(1)
    expect(retry.mock.calls[0]![0]).toBe('old')
    expect(retry.mock.calls[0]![1]).toEqual({ idempotency_key: expect.stringMatching(/^[0-9a-f-]{36}$/i) })
    finish(task('queued', 'new'))
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/research/new')
  })

  it('keeps the same key after an ambiguous error and displays errors separately from polling', async () => {
    const { wrapper } = await setup()
    const retry = vi.spyOn(api.tasks, 'retry').mockRejectedValueOnce(new Error('请先配置个人默认模型')).mockRejectedValueOnce('offline')
    await wrapper.get('[data-test="retry-task"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="retry-error"]').text()).toContain('请先配置个人默认模型')
    expect(wrapper.text()).toContain('原任务错误')
    expect(wrapper.text()).not.toContain('重新同步')
    await wrapper.get('[data-test="retry-task"]').trigger('click')
    await flushPromises()
    expect(retry.mock.calls[0]![1]).toEqual(retry.mock.calls[1]![1])
    expect(wrapper.get('[data-test="retry-error"]').text()).toContain('暂未收到重试结果')
  })

  it('resets retry intent on task route changes and ignores the old response', async () => {
    const { wrapper, router } = await setup()
    let finish!: (value: Task) => void
    const retry = vi.spyOn(api.tasks, 'retry').mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockRejectedValue(new Error('连接中断'))
    await wrapper.get('[data-test="retry-task"]').trigger('click')
    await router.push('/research/other')
    await flushPromises()
    expect(wrapper.get('[data-test="retry-task"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-test="retry-task"]').trigger('click')
    await flushPromises()
    expect(retry.mock.calls[1]![0]).toBe('other')
    expect(retry.mock.calls[0]![1]).not.toEqual(retry.mock.calls[1]![1])
    finish(task('queued', 'stale'))
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/research/other')
    expect(wrapper.get('[data-test="retry-error"]').text()).toContain('连接中断')
  })

  it('completes a pending retry when only the task query or hash changes', async () => {
    const { wrapper, router } = await setup()
    let finish!: (value: Task) => void
    const retry = vi.spyOn(api.tasks, 'retry').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('[data-test="retry-task"]').trigger('click')
    await router.push('/research/old?view=progress#main-content')
    expect(wrapper.get('[data-test="retry-task"]').attributes('disabled')).toBeDefined()
    expect(retry).toHaveBeenCalledTimes(1)
    finish(task('queued', 'new'))
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/research/new')
  })

  it('ignores a retry response after leaving for another route', async () => {
    const { wrapper, router } = await setup()
    let finish!: (value: Task) => void
    vi.spyOn(api.tasks, 'retry').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('[data-test="retry-task"]').trigger('click')
    await router.push('/settings')
    finish(task('queued', 'stale'))
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/settings')
  })

  it('does not navigate when a retry resolves after unmount', async () => {
    const { wrapper, router } = await setup()
    let finish!: (value: Task) => void
    vi.spyOn(api.tasks, 'retry').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('[data-test="retry-task"]').trigger('click')
    const push = vi.spyOn(router, 'push')
    wrapper.unmount()
    wrappers.splice(wrappers.indexOf(wrapper), 1)
    finish(task('queued', 'stale'))
    await flushPromises()
    expect(push).not.toHaveBeenCalled()
  })
})
