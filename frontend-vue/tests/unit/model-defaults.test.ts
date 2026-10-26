import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import ResearchNewView from '../../src/views/ResearchNewView.vue'
import { api } from '../../src/api'
import type { ModelSettings } from '../../src/types'
afterEach(() => vi.restoreAllMocks())
const settings: ModelSettings = { default_provider: 'openai', providers: [{ provider: 'qwen', configured: true, model: 'personal-qwen', key_hint: '1234' }, { provider: 'openai', configured: true, model: 'personal-openai', key_hint: '5678' }] }
async function setup(study = false) {
  vi.spyOn(api.collections, 'list').mockResolvedValue({ collections: [], total: 0, page: 0, size: 100 })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/research/new', component: ResearchNewView }, { path: '/research', component: { template: '<div />' } }, { path: '/settings', component: { template: '<div />' } }] })
  await router.push('/research/new' + (study ? '?task_type=study_report' : ''))
  return mount(ResearchNewView, { global: { plugins: [router] } })
}
it.each([false, true])('loads personal provider and model for new tasks (study=%s)', async study => {
  vi.spyOn(api.modelSettings, 'get').mockResolvedValue(settings)
  const wrapper = await setup(study)
  await flushPromises()
  expect((wrapper.get('[data-test="task-provider"]').element as HTMLSelectElement).value).toBe('openai')
  expect((wrapper.get('[data-test="task-model"]').element as HTMLInputElement).value).toBe('personal-openai')
  await wrapper.get('[data-test="task-provider"]').setValue('qwen')
  expect((wrapper.get('[data-test="task-model"]').element as HTMLInputElement).value).toBe('personal-qwen')
  await wrapper.get('[data-test="task-model"]').setValue('manual-override')
  await wrapper.get('[data-test="task-provider"]').setValue('openai')
  expect((wrapper.get('[data-test="task-model"]').element as HTMLInputElement).value).toBe('manual-override')
  expect(wrapper.get('a[href="/settings"]').text()).toContain('个人设置')
  wrapper.unmount()
})
it('preserves edits made before settings arrive', async () => {
  let resolve!: (settings: ModelSettings) => void
  vi.spyOn(api.modelSettings, 'get').mockImplementation(() => new Promise(done => { resolve = done }))
  const wrapper = await setup()
  await wrapper.get('[data-test="task-provider"]').setValue('qwen')
  await wrapper.get('[data-test="task-model"]').setValue('typed-model')
  resolve(settings)
  await flushPromises()
  expect((wrapper.get('[data-test="task-provider"]').element as HTMLSelectElement).value).toBe('qwen')
  expect((wrapper.get('[data-test="task-model"]').element as HTMLInputElement).value).toBe('typed-model')
  wrapper.unmount()
})
it('keeps demo usable when defaults fail to load', async () => {
  vi.spyOn(api.modelSettings, 'get').mockRejectedValue(new Error('offline'))
  const create = vi.spyOn(api.tasks, 'create').mockRejectedValue(new Error('offline'))
  const wrapper = await setup()
  await flushPromises()
  await wrapper.get('textarea').setValue('demo')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(create).toHaveBeenCalledWith(expect.objectContaining({ mode: 'demo', provider: 'qwen' }))
  wrapper.unmount()
})
it('omits untouched provider for the selected server default in live mode', async () => {
  vi.spyOn(api.modelSettings, 'get').mockResolvedValue({ ...settings, default_provider: null })
  const create = vi.spyOn(api.tasks, 'create').mockRejectedValue(new Error('offline'))
  const wrapper = await setup()
  await flushPromises()
  await wrapper.get('textarea').setValue('live research')
  const mode = wrapper.findAll('select').find(select => select.find('option[value="live"]').exists())!
  await mode.setValue('live')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(create.mock.calls[0]![0]).not.toHaveProperty('provider')
  expect(create.mock.calls[0]![0]).not.toHaveProperty('model')
  await wrapper.get('[data-test="task-provider"]').setValue('qwen')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(create.mock.calls[1]![0]).toMatchObject({ provider: 'qwen', model: 'personal-qwen' })
  wrapper.unmount()
})
it.each(['pending', 'failed'])('lets backend resolve account defaults when settings are %s during live submission', async state => {
  let resolve!: (settings: ModelSettings) => void
  vi.spyOn(api.modelSettings, 'get').mockImplementation(() => state === 'failed' ? Promise.reject(new Error('offline')) : new Promise(done => { resolve = done }))
  const create = vi.spyOn(api.tasks, 'create').mockRejectedValue(new Error('offline'))
  const wrapper = await setup()
  await flushPromises()
  await wrapper.get('textarea').setValue('live research')
  await wrapper.findAll('select').find(select => select.find('option[value="live"]').exists())!.setValue('live')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(create.mock.calls[0]![0]).not.toHaveProperty('provider')
  await wrapper.get('[data-test="task-provider"]').setValue('qwen')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(create.mock.calls[1]![0]).toHaveProperty('provider', 'qwen')
  if (state === 'pending') {
    resolve(settings)
    await flushPromises()
    expect((wrapper.get('[data-test="task-provider"]').element as HTMLSelectElement).value).toBe('qwen')
  }
  wrapper.unmount()
})
