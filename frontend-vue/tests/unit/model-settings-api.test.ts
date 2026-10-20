import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../../src/api'
import { request } from '../../src/api/http'
vi.mock('../../src/api/http', () => ({ request: vi.fn().mockResolvedValue({}) }))
afterEach(() => vi.clearAllMocks())
it('provides saved model settings operations with a bounded connection test', async () => {
  expect(api).toHaveProperty('modelSettings')
  const settings = (api as any).modelSettings
  await settings.get()
  expect(request).toHaveBeenLastCalledWith('/model-settings')
  await settings.save('qwen', { model: 'custom', api_key: '' })
  expect(request).toHaveBeenLastCalledWith('/model-settings/qwen', { method: 'PUT', body: { model: 'custom', api_key: '' } })
  await settings.setDefault(null)
  expect(request).toHaveBeenLastCalledWith('/model-settings/default', { method: 'PUT', body: { provider: null } })
  await settings.removeKey('openai')
  expect(request).toHaveBeenLastCalledWith('/model-settings/openai/key', { method: 'DELETE' })
  await settings.test('qwen')
  expect(request).toHaveBeenLastCalledWith('/model-settings/qwen/test', { method: 'POST', timeoutMs: 25000 })
})
