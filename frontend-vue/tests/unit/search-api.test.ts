import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../../src/api'
import { request } from '../../src/api/http'

vi.mock('../../src/api/http', () => ({ request: vi.fn().mockResolvedValue({}) }))
beforeEach(() => vi.clearAllMocks())

it('sends long structured terms once so Chinese searches fit the server request limit', async () => {
  const text = '中'.repeat(500)
  await api.papers.search(text, 'arxiv', 10, 1, 'relevance', [{ text, match_mode: 'fuzzy' }])
  const target = vi.mocked(request).mock.calls[0]![0] as string
  expect(new URL(target, 'http://localhost').searchParams.has('query')).toBe(false)
  expect(target.length).toBeLessThan(6000)
})

it('preserves the single-query legacy API', async () => {
  await api.papers.search('agents', 'arxiv', 10)
  const target = vi.mocked(request).mock.calls[0]![0] as string
  expect(new URL(target, 'http://localhost').searchParams.get('query')).toBe('agents')
})
