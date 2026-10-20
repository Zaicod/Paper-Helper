import type { CsrfToken } from '../types'

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = 'ApiError' }
}
let csrf: CsrfToken | null = null
let csrfRequest: Promise<CsrfToken> | null = null
let onUnauthorized = () => {}
export function setUnauthorizedHandler(handler: () => void) { onUnauthorized = handler }
export function resetCsrf() { csrf = null; csrfRequest = null }

async function send<T>(path: string, method: string, body?: unknown, token?: CsrfToken, timeoutMs = 20000): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const headers = new Headers({ Accept: 'application/json' })
    if (body !== undefined) headers.set('Content-Type', 'application/json')
    if (token) headers.set(token.header_name, token.token)
    const response = await fetch(`/api${path}`, { method, headers, credentials: 'same-origin', signal: controller.signal, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
    if (response.status === 401) { resetCsrf(); onUnauthorized() }
    if (response.status === 204 && response.ok) return undefined as T
    let result: { code?: number; msg?: string; data?: T }
    try { result = await response.json() }
    catch { throw new ApiError(response.status, '服务暂时不可用，请稍后重试。') }
    if (!response.ok || result.code !== 1) throw new ApiError(response.status, typeof result.msg === 'string' && result.msg ? result.msg : '请求未能完成，请稍后重试。')
    return result.data as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(0, '连接暂时中断，请检查网络后重试。')
  } finally { clearTimeout(timeout) }
}
async function getCsrf(): Promise<CsrfToken> {
  if (csrf) return csrf
  csrfRequest ??= send<CsrfToken>('/auth/csrf', 'GET').then(value => { csrf = value; return value }).finally(() => { csrfRequest = null })
  return csrfRequest
}
export async function request<T = void>(path: string, options: { method?: string; body?: unknown; timeoutMs?: number } = {}): Promise<T> {
  const method = options.method || 'GET'
  const write = !['GET', 'HEAD'].includes(method)
  const token = write ? await getCsrf() : undefined
  try {
    const result = await send<T>(path, method, options.body, token, options.timeoutMs)
    if (['/auth/login', '/auth/register', '/auth/logout'].includes(path)) resetCsrf()
    return result
  } catch (error) {
    if (error instanceof ApiError && error.status === 403 && write) {
      resetCsrf()
      try { await getCsrf() } catch { /* Preserve the original failure and never replay the operation. */ }
      throw new ApiError(403, '安全验证已更新，请重试刚才的操作。')
    }
    throw error
  }
}
