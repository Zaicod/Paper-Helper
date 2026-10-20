import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import { ApiError, resetCsrf } from '../api/http'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const initialized = ref(false)
  let restoring: Promise<void> | null = null
  async function restore() {
    if (initialized.value) return
    restoring ??= api.auth.me().then(value => { user.value = value; initialized.value = true }).catch(error => {
      if (!(error instanceof ApiError && error.status === 401)) throw error
      user.value = null; initialized.value = true
    }).finally(() => { restoring = null })
    return restoring
  }
  function clear() { user.value = null; initialized.value = true; resetCsrf() }
  async function login(input: { identifier: string; password: string }) { user.value = await api.auth.login(input); initialized.value = true }
  async function register(input: { username: string; email: string; password: string }) { user.value = await api.auth.register(input); initialized.value = true }
  async function logout() { await api.auth.logout(); clear() }
  return { user, initialized, restore, clear, login, register, logout }
})
