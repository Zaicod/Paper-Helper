import { request } from './http'
import type { User, Collection, CollectionPage, CollectionDetail, Paper, PaperInput, PaperSource, PaperSort, PaperSearchResult, SearchKeyword, Task, TaskInput, TaskPage, TaskCategory, ModelProvider, ModelSettings } from '../types'
const collections = '/library/collections'
const tasks = '/research/tasks'
export const api = {
  modelSettings: {
    get: () => request<ModelSettings>('/model-settings'),
    save: (provider: ModelProvider, body: { model: string; api_key?: string | null }) => request('/model-settings/' + provider, { method: 'PUT', body }),
    setDefault: (provider: ModelProvider | null) => request('/model-settings/default', { method: 'PUT', body: { provider } }),
    removeKey: (provider: ModelProvider) => request('/model-settings/' + provider + '/key', { method: 'DELETE' }),
    test: (provider: ModelProvider) => request<{ success: boolean; message: string }>('/model-settings/' + provider + '/test', { method: 'POST', timeoutMs: 25000 }),
  },
  papers: {
    search: (query: string, source: PaperSource, limit: number, page = 1, sort: PaperSort = 'relevance', keywords?: SearchKeyword[]) => request<PaperSearchResult>(`/papers/search?${new URLSearchParams({ source, limit: String(limit), page: String(page), sort, ...(keywords === undefined ? { query } : { keywords: JSON.stringify(keywords) }) })}`, { timeoutMs: 30000 }),
  },
  auth: {
    me: () => request<User>('/auth/me'),
    login: (body: { identifier: string; password: string }) => request<User>('/auth/login', { method: 'POST', body }),
    register: (body: { username: string; email: string; password: string }) => request<User>('/auth/register', { method: 'POST', body }),
    logout: () => request('/auth/logout', { method: 'POST' }),
  },
  collections: {
    list: (query = '', page = 0, size = 12) => request<CollectionPage>(`${collections}?${new URLSearchParams({ query, page: String(page), size: String(size) })}`),
    get: (id: number) => request<CollectionDetail>(`${collections}/${id}`),
    create: (body: { name: string; description: string }) => request<Collection>(collections, { method: 'POST', body }),
    update: (id: number, body: { name: string; description: string }) => request<Collection>(`${collections}/${id}`, { method: 'PUT', body }),
    remove: (id: number) => request(`${collections}/${id}`, { method: 'DELETE' }),
    note: (id: number, content: string) => request<{ content: string }>(`${collections}/${id}/note`, { method: 'PUT', body: { content } }),
    addPaper: (id: number, body: PaperInput) => request<Paper>(`${collections}/${id}/papers`, { method: 'POST', body }),
    paper: (id: number, paper: number) => request<Paper>(`${collections}/${id}/papers/${paper}`),
    updatePaper: (id: number, paper: number, body: PaperInput) => request<Paper>(`${collections}/${id}/papers/${paper}`, { method: 'PUT', body }),
    removePaper: (id: number, paper: number) => request(`${collections}/${id}/papers/${paper}`, { method: 'DELETE' }),
    paperNote: (id: number, body: { source: string; paper_id: string; content: string }) => request<{ content: string }>(`${collections}/${id}/paper-note`, { method: 'PUT', body }),
  },
  tasks: {
    list: (page = 0, size = 10, category?: TaskCategory, keyword = '') => request<TaskPage>(`${tasks}?${new URLSearchParams({ page: String(page), size: String(size), ...(category ? { category } : {}), ...(keyword ? { keyword } : {}) })}`),
    get: (id: string) => request<Task>(`${tasks}/${encodeURIComponent(id)}`),
    create: (body: TaskInput) => request<Task>(tasks, { method: 'POST', body }),
    retry: (id: string, body: { idempotency_key: string }) => request<Task>(`${tasks}/${encodeURIComponent(id)}/retry`, { method: 'POST', body }),
  },
}
