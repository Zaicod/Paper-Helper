import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia } from 'pinia'
import { useAuthStore } from '../../src/stores/auth'
import ModelSettingsView from '../../src/views/ModelSettingsView.vue'
import { api } from '../../src/api'
const stored = () => ({ default_provider: 'qwen' as const, providers: [
  { provider: 'qwen' as const, model: 'saved-qwen', configured: true, key_hint: '••••1234' },
  { provider: 'openai' as const, model: 'gpt-5.6-luna', configured: false, key_hint: null },
] })
beforeEach(() => { vi.spyOn(api.modelSettings, 'get').mockResolvedValue(stored()) })
afterEach(() => vi.restoreAllMocks())
async function setup() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/model-settings', component: ModelSettingsView }, { path: '/research/new', component: { template: '<div />' } }] })
  await router.push('/model-settings')
  const pinia = createPinia()
  useAuthStore(pinia).user = { id: 7, username: 'personal-learner', email: 'learner@example.test', created_at: '2026-10-19T00:00:00Z' }
  const wrapper = mount(ModelSettingsView, { global: { plugins: [router, pinia] } })
  await flushPromises()
  return wrapper
}
it('shows the current account and its saved default model in personal settings', async () => {
  const wrapper = await setup()
  expect(wrapper.get('h1').text()).toBe('个人设置')
  expect(wrapper.text()).toContain('personal-learner')
  expect(wrapper.text()).toContain('learner@example.test')
  expect(wrapper.get('[data-test="current-model"]').text()).toContain('saved-qwen')
  expect((wrapper.get('[data-test="default-model-provider"]').element as HTMLSelectElement).value).toBe('qwen')
  wrapper.unmount()
})
it('persists the personal default selection and makes the environment choice explicit', async () => {
  const setDefault = vi.spyOn(api.modelSettings, 'setDefault').mockResolvedValue(undefined)
  const wrapper = await setup()
  await wrapper.get('[data-test="default-model-provider"]').setValue('server')
  await wrapper.get('[data-test="default-model-form"]').trigger('submit')
  await flushPromises()
  expect(setDefault).toHaveBeenCalledWith(null)
  expect(wrapper.text()).toContain('环境变量')
  wrapper.unmount()
})
it('shows masked saved configuration and only blank password inputs', async () => {
  const wrapper = await setup()
  expect(wrapper.text()).toContain('••••1234')
  expect(wrapper.findAll('input[type="password"]')).toHaveLength(2)
  expect((wrapper.get('[data-test="qwen-key"]').element as HTMLInputElement).value).toBe('')
  expect((wrapper.get('[data-test="qwen-model"]').element as HTMLInputElement).value).toBe('saved-qwen')
  expect(wrapper.text()).toContain('可能消耗少量额度')
  wrapper.unmount()
})
it('saves a replacement key then clears it, and preserves saved key on a blank save', async () => {
  const save = vi.spyOn(api.modelSettings, 'save').mockResolvedValue(undefined)
  const wrapper = await setup()
  await wrapper.get('[data-test="qwen-key"]').setValue('sk-private')
  await wrapper.get('[data-test="qwen-model"]').setValue('custom-model')
  await wrapper.get('[data-test="qwen-form"]').trigger('submit')
  await flushPromises()
  expect(save).toHaveBeenLastCalledWith('qwen', { model: 'custom-model', api_key: 'sk-private' })
  expect((wrapper.get('[data-test="qwen-key"]').element as HTMLInputElement).value).toBe('')
  await wrapper.get('[data-test="qwen-form"]').trigger('submit')
  await flushPromises()
  expect(save).toHaveBeenLastCalledWith('qwen', { model: 'saved-qwen' })
  expect(localStorage.getItem('api_key')).toBeNull()
  wrapper.unmount()
})
it('confirms deletion separately, changes default and tests only saved configuration', async () => {
  const remove = vi.spyOn(api.modelSettings, 'removeKey').mockResolvedValue(undefined)
  const setDefault = vi.spyOn(api.modelSettings, 'setDefault').mockResolvedValue(undefined)
  const test = vi.spyOn(api.modelSettings, 'test').mockResolvedValue({ success: false, message: '请检查账号权限。' })
  const wrapper = await setup()
  await wrapper.get('[data-test="qwen-key"]').setValue('unsaved-secret')
  await wrapper.get('[data-test="qwen-test"]').trigger('click')
  await flushPromises()
  expect(test).toHaveBeenCalledWith('qwen')
  expect(wrapper.text()).toContain('请检查账号权限。')
  await wrapper.get('[data-test="qwen-delete"]').trigger('click')
  expect(remove).not.toHaveBeenCalled()
  await wrapper.get('[data-test="qwen-confirm-delete"]').trigger('click')
  await flushPromises()
  expect(remove).toHaveBeenCalledWith('qwen')
  await wrapper.get('[data-test="server-default"]').trigger('click')
  await flushPromises()
  expect(setDefault).toHaveBeenCalledWith(null)
  wrapper.unmount()
})
it('keeps save failures visible without displaying the entered secret', async () => {
  vi.spyOn(api.modelSettings, 'save').mockRejectedValue(new Error('保存失败，请重试。'))
  const wrapper = await setup()
  await wrapper.get('[data-test="qwen-key"]').setValue('sk-private')
  await wrapper.get('[data-test="qwen-form"]').trigger('submit')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('保存失败')
  expect(wrapper.text()).not.toContain('sk-private')
  wrapper.unmount()
})
