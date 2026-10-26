import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../../src/api'
import { resetCsrf } from '../../src/api/http'
const response = (data: unknown) => new Response(JSON.stringify({code:1,data}))
afterEach(() => {vi.unstubAllGlobals(); resetCsrf()})
it('uploads a PDF as multipart with session and CSRF without a JSON content type', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(response({token:'csrf', header_name:'X-CSRF-TOKEN'})).mockResolvedValueOnce(response({status:'ready'}))
  vi.stubGlobal('fetch', fetcher)
  const file = new File(['%PDF-test'], 'paper.pdf', {type:'application/pdf'})
  await api.documents.upload(7, 2, file)
  const [path, options] = fetcher.mock.calls[1]!
  expect(path).toBe('/api/library/collections/7/papers/2/document')
  expect(options.body).toBeInstanceOf(FormData)
  expect(options.body.get('file')).toBe(file)
  expect(new Headers(options.headers).has('Content-Type')).toBe(false)
  expect(new Headers(options.headers).get('X-CSRF-TOKEN')).toBe('csrf')
  expect(options.credentials).toBe('same-origin')
})
it('reads status and posts repair with a stable supplied idempotency key', async () => {
  const fetcher = vi.fn().mockImplementation(async () => response({token:'csrf',header_name:'X-CSRF-TOKEN'}))
  vi.stubGlobal('fetch', fetcher)
  await api.documents.get(7,2)
  await api.tasks.repair('old/id', {idempotency_key:'key'})
  expect(fetcher.mock.calls[0]![0]).toBe('/api/library/collections/7/papers/2/document')
  expect(fetcher.mock.calls[2]![0]).toBe('/api/research/tasks/old%2Fid/repair')
  expect(JSON.parse(fetcher.mock.calls[2]![1].body)).toEqual({idempotency_key:'key'})
})
