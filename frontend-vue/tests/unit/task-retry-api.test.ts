import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../../src/api'
import { request } from '../../src/api/http'
vi.mock('../../src/api/http', () => ({ request: vi.fn().mockResolvedValue({ task_id: 'new' }) }))
afterEach(() => vi.clearAllMocks())
it('posts only the retry intent key to the encoded original task route', async () => {
  expect(api.tasks).toHaveProperty('retry')
  const result = await api.tasks.retry('old/id', { idempotency_key: 'intent-key' })
  expect(request).toHaveBeenCalledWith('/research/tasks/old%2Fid/retry', { method: 'POST', body: { idempotency_key: 'intent-key' } })
  expect(result.task_id).toBe('new')
})
