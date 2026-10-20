import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ResearchView from '../../src/views/ResearchView.vue'
import { api } from '../../src/api'
import type { TaskPage } from '../../src/types'

const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.restoreAllMocks() })
function result(topic = '最新任务', page = 0, total = 12): TaskPage {
  return { page, size: 10, total, tasks: [{ task_id: topic, topic, status: 'running', created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z' }] }
}
async function setup(url = '/research') {
  const list = vi.spyOn(api.tasks, 'list').mockResolvedValue(result())
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/research', component: ResearchView },
    { path: '/research/:id', component: { template: '<p>detail</p>' } },
  ] })
  await router.push(url)
  const wrapper = mount(ResearchView, { global: { plugins: [router] } })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router, list }
}
it('defaults to active and switches three categories at ten rows per page', async () => {
  const { wrapper, list } = await setup()
  expect(list).toHaveBeenLastCalledWith(0, 10, 'active', '')
  await wrapper.get('[data-test="tab-history"]').trigger('click'); await flushPromises()
  expect(list).toHaveBeenLastCalledWith(0, 10, 'history', '')
  expect(wrapper.get('[data-test="tab-history"]').attributes('aria-selected')).toBe('true')
  await wrapper.get('[data-test="tab-unfinished"]').trigger('click'); await flushPromises()
  expect(list).toHaveBeenLastCalledWith(0, 10, 'unfinished', '')
})
it('restores route search and page, searches on submit and resets page', async () => {
  const { wrapper, router, list } = await setup('/research?category=history&keyword=Agent&page=2')
  expect(list).toHaveBeenLastCalledWith(1, 10, 'history', 'Agent')
  expect(wrapper.get<HTMLInputElement>('input[type="search"]').element.value).toBe('Agent')
  await wrapper.get('input[type="search"]').setValue(' 多模态 ')
  expect(list).toHaveBeenCalledTimes(1)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(list).toHaveBeenLastCalledWith(0, 10, 'history', '多模态')
  expect(router.currentRoute.value.query.page).toBe('1')
  await wrapper.get('[data-test="clear-search"]').trigger('click'); await flushPromises()
  expect(list).toHaveBeenLastCalledWith(0, 10, 'history', '')
})
it('paginates and preserves search while switching categories returns to first page', async () => {
  const { wrapper, router, list } = await setup('/research?category=history&keyword=Agent')
  list.mockResolvedValue(result('第二页', 1))
  await wrapper.get('[data-test="next-page"]').trigger('click'); await flushPromises()
  expect(list).toHaveBeenLastCalledWith(1, 10, 'history', 'Agent')
  expect(router.currentRoute.value.query.page).toBe('2')
  expect(wrapper.get('[data-test="next-page"]').attributes('disabled')).toBeDefined()
  list.mockResolvedValue(result())
  await wrapper.get('[data-test="tab-active"]').trigger('click'); await flushPromises()
  expect(list).toHaveBeenLastCalledWith(0, 10, 'active', 'Agent')
})
it('ignores stale responses when switching lists quickly', async () => {
  const { wrapper, list } = await setup()
  let finish!: (value: TaskPage) => void
  list.mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValue(result('未完成记录'))
  await wrapper.get('[data-test="tab-history"]').trigger('click'); await flushPromises()
  expect(wrapper.text()).not.toContain('最新任务')
  await wrapper.get('[data-test="tab-unfinished"]').trigger('click'); await flushPromises()
  finish(result('过时的历史记录')); await flushPromises()
  expect(wrapper.text()).toContain('未完成记录')
  expect(wrapper.text()).not.toContain('过时的历史记录')
})
it('offers refresh and distinguishes no search results from an empty category', async () => {
  const { wrapper, list } = await setup()
  list.mockResolvedValue({ tasks: [], page: 0, size: 10, total: 0 })
  await wrapper.get('[data-test="refresh-tasks"]').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('暂无进行中的研究')
  await wrapper.get('input[type="search"]').setValue('查不到')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.text()).toContain('没有匹配的研究记录')
})
it('clears stale rows on error and retries the current filter', async () => {
  const { wrapper, list } = await setup()
  list.mockRejectedValueOnce(new Error('读取失败'))
  await wrapper.get('[data-test="tab-history"]').trigger('click'); await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('读取失败')
  expect(wrapper.find('.task-row').exists()).toBe(false)
  await wrapper.get('[data-test="retry-list"]').trigger('click'); await flushPromises()
  expect(list).toHaveBeenLastCalledWith(0, 10, 'history', '')
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
})
it('returns to a valid page when active tasks leave the list', async () => {
  const { wrapper, router, list } = await setup()
  list.mockResolvedValueOnce({ tasks: [], total: 1, page: 1, size: 10 }).mockResolvedValue(result('剩余任务', 0, 1))
  await wrapper.get('[data-test="next-page"]').trigger('click'); await flushPromises()
  expect(router.currentRoute.value.query.page).toBe('1')
  expect(wrapper.text()).toContain('剩余任务')
  expect(list).toHaveBeenLastCalledWith(0, 10, 'active', '')
})
it('supports arrow navigation and preserves filters after browser back', async () => {
  const { wrapper, router, list } = await setup('/research?category=history&keyword=Agent&page=2')
  await wrapper.get('[data-test="tab-history"]').trigger('keydown', { key: 'ArrowLeft' }); await flushPromises()
  expect(list).toHaveBeenLastCalledWith(0, 10, 'unfinished', 'Agent')
  router.back(); await new Promise(resolve => setTimeout(resolve, 20)); await flushPromises()
  expect(list).toHaveBeenLastCalledWith(1, 10, 'history', 'Agent')
})
