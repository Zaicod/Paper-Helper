import { expect, it, vi } from 'vitest'
import { api } from '../../src/api'
import { request } from '../../src/api/http'
vi.mock('../../src/api/http', () => ({ request: vi.fn().mockResolvedValue({}) }))
it('encodes history search and defaults to ten rows', async () => {
  await api.tasks.list(1, 10, 'history', '多模态 & Agent')
  const params = new URL(vi.mocked(request).mock.calls.at(-1)![0], 'http://localhost').searchParams
  expect(Object.fromEntries(params)).toEqual({ page: '1', size: '10', category: 'history', keyword: '多模态 & Agent' })
  await api.tasks.list()
  expect(new URL(vi.mocked(request).mock.calls.at(-1)![0], 'http://localhost').searchParams.get('size')).toBe('10')
})
