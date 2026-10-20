import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import LoginView from '../../src/views/LoginView.vue'
import { useAuthStore } from '../../src/stores/auth'
import { api } from '../../src/api'
const { push, route } = vi.hoisted(() => ({ push: vi.fn(), route: { query: {} as Record<string, string> } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => route }))
vi.mock('../../src/api', () => ({ api: { auth: { login: vi.fn(), register: vi.fn(), me: vi.fn(), logout: vi.fn() } } }))
beforeEach(() => { vi.resetAllMocks(); setActivePinia(createPinia()); route.query = {} })
describe('login and session lifecycle', () => {
  it('signs in and never navigates to an external redirect', async () => {
    route.query.redirect = '//evil.example'
    vi.mocked(api.auth.login).mockResolvedValue({ id: 1, username: 'reader', email: 'a@b.test', created_at: '' })
    const page = mount(LoginView)
    await page.get('[name="identifier"]').setValue('reader')
    await page.get('[name="password"]').setValue('long-password')
    await page.get('form').trigger('submit'); await flushPromises()
    expect(useAuthStore().user?.username).toBe('reader')
    expect(push).toHaveBeenCalledWith('/collections')
  })
  it('retains a failed login and permits explicit retry', async () => {
    vi.mocked(api.auth.login).mockRejectedValueOnce(new Error('用户名、邮箱或密码错误')).mockResolvedValueOnce({ id: 1, username: 'reader', email: 'a@b.test', created_at: '' })
    const page = mount(LoginView)
    await page.get('[name="identifier"]').setValue('reader')
    await page.get('[name="password"]').setValue('long-password')
    await page.get('form').trigger('submit'); await flushPromises()
    expect(page.get('[role="alert"]').text()).toContain('密码错误')
    expect(push).not.toHaveBeenCalled()
    await page.get('form').trigger('submit'); await flushPromises()
    expect(api.auth.login).toHaveBeenCalledTimes(2)
  })
  it('restores a saved server session only once across simultaneous guards', async () => {
    vi.mocked(api.auth.me).mockResolvedValue({ id: 1, username: 'reader', email: 'a@b.test', created_at: '' })
    const auth = useAuthStore()
    await Promise.all([auth.restore(), auth.restore()]); await auth.restore()
    expect(api.auth.me).toHaveBeenCalledOnce()
    expect(auth.user?.id).toBe(1)
  })
})
