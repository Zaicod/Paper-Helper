import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { request, resetCsrf, setUnauthorizedHandler } from '../../src/api/http'

const response = (data: unknown, status = 200) => new Response(JSON.stringify({ code: status < 400 ? 1 : 0, msg: status < 400 ? null : data, data: status < 400 ? data : null }), { status, headers: { 'Content-Type': 'application/json' } })
const csrf = () => response({ token: 'masked-token', header_name: 'X-CSRF-TOKEN' })
beforeEach(() => { resetCsrf(); setUnauthorizedHandler(() => {}); vi.stubGlobal('fetch', vi.fn()) })
afterEach(() => vi.unstubAllGlobals())

describe('Java HTTP boundary', () => {
  it('unwraps Result and sends the browser session', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response({ id: 7 }))
    expect(await request('/auth/me')).toEqual({ id: 7 })
    expect(fetch).toHaveBeenCalledWith('/api/auth/me', expect.objectContaining({ credentials: 'same-origin' }))
  })
  it('obtains CSRF before a write and encodes JSON once', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(csrf()).mockResolvedValueOnce(response({ id: 1 }, 201))
    await request('/library/collections', { method: 'POST', body: { name: '证据' } })
    expect(fetch).toHaveBeenCalledTimes(2)
    const options = vi.mocked(fetch).mock.calls[1]![1]!
    expect(new Headers(options.headers).get('X-CSRF-TOKEN')).toBe('masked-token')
    expect(JSON.parse(String(options.body))).toEqual({ name: '证据' })
  })
  it('invalidates the pre-login token before the next write', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(csrf()).mockResolvedValueOnce(response({ username: 'reader' }))
      .mockResolvedValueOnce(csrf()).mockResolvedValueOnce(response({ id: 1 }, 201))
    await request('/auth/login', { method: 'POST', body: { identifier: 'reader', password: 'secret' } })
    await request('/library/collections', { method: 'POST', body: { name: 'Notes' } })
    expect(vi.mocked(fetch).mock.calls.filter(([path]) => path === '/api/auth/csrf')).toHaveLength(2)
  })
  it('refreshes expired CSRF without automatically replaying a write', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(csrf()).mockResolvedValueOnce(response('expired', 403)).mockResolvedValueOnce(csrf())
    await expect(request('/library/collections', { method: 'POST', body: { name: 'Notes' } })).rejects.toMatchObject({ status: 403 })
    expect(vi.mocked(fetch).mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
  })
  it('clears user identity on 401 and uses safe network errors', async () => {
    const expired = vi.fn(); setUnauthorizedHandler(expired)
    vi.mocked(fetch).mockResolvedValueOnce(response('请先登录', 401))
    await expect(request('/auth/me')).rejects.toMatchObject({ status: 401 })
    expect(expired).toHaveBeenCalledOnce()
    vi.mocked(fetch).mockRejectedValueOnce(new Error('raw-secret-stack'))
    await expect(request('/research/tasks')).rejects.toThrow('连接暂时中断')
  })
  it('handles empty 204 and rejects HTML responses without exposing their contents', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(csrf()).mockResolvedValueOnce(new Response(null, { status: 204 }))
    await expect(request('/auth/logout', { method: 'POST' })).resolves.toBeUndefined()
    vi.mocked(fetch).mockResolvedValueOnce(new Response('<html>secret-proxy-error</html>', { status: 502 }))
    await expect(request('/auth/me')).rejects.toThrow('服务暂时不可用')
  })
})
