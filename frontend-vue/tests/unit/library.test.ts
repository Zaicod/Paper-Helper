import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import CollectionsView from '../../src/views/CollectionsView.vue'
import CollectionDetailView from '../../src/views/CollectionDetailView.vue'
import { api } from '../../src/api'

vi.mock('../../src/api', () => ({ api: { collections: {
  list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(),
  note: vi.fn(), addPaper: vi.fn(), removePaper: vi.fn(), paperNote: vi.fn(),
} } }))

const collection = { id: 7, name: '我的研究', description: '保留可追溯的证据', paper_count: 0 }

async function render(component: typeof CollectionsView | typeof CollectionDetailView, path = '/collections') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/collections', component: CollectionsView },
    { path: '/collections/:id', component: CollectionDetailView },
    { path: '/research/new', component: { template: '<div />' } },
  ] })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.collections.list).mockResolvedValue({ collections: [collection], total: 1, page: 0, size: 12 })
  vi.mocked(api.collections.get).mockResolvedValue({ ...collection, overall_note: '原有笔记', papers: [] })
})

describe('library collection workflows', () => {
  it('creates from the entered name and refreshes owned collections, preserving a failed form for retry', async () => {
    vi.mocked(api.collections.create).mockRejectedValueOnce(new Error('已有同名收藏夹')).mockResolvedValueOnce(collection)
    const wrapper = await render(CollectionsView)
    await wrapper.get('#collection-name').setValue(' 我的研究 ')
    await wrapper.get('#collection-description').setValue('保留可追溯的证据')
    await wrapper.get('[data-test="collection-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('已有同名收藏夹')
    expect((wrapper.get('#collection-name').element as HTMLInputElement).value).toBe(' 我的研究 ')
    await wrapper.get('[data-test="collection-form"]').trigger('submit')
    await flushPromises()
    expect(api.collections.create).toHaveBeenLastCalledWith({ name: '我的研究', description: '保留可追溯的证据' })
    expect(api.collections.list).toHaveBeenCalledTimes(2)
    expect((wrapper.get('#collection-name').element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })

  it('requires confirmation before deleting a collection', async () => {
    const confirmation = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = await render(CollectionsView)
    await wrapper.get('[data-test="delete-collection"]').trigger('click')
    expect(api.collections.remove).not.toHaveBeenCalled()
    confirmation.mockReturnValue(true)
    await wrapper.get('[data-test="delete-collection"]').trigger('click')
    await flushPromises()
    expect(api.collections.remove).toHaveBeenCalledWith(7)
    confirmation.mockRestore()
    wrapper.unmount()
  })

  it('parses manual metadata into arrays and saves a collection note to the route owner resource', async () => {
    const wrapper = await render(CollectionDetailView, '/collections/7')
    await wrapper.get('#overall-note').setValue('可核查的证据说明')
    await wrapper.get('[data-test="collection-note-form"]').trigger('submit')
    await flushPromises()
    expect(api.collections.note).toHaveBeenCalledWith(7, '可核查的证据说明')
    await wrapper.get('#paper-source').setValue('manual')
    await wrapper.get('#paper-id').setValue('paper-1')
    await wrapper.get('#paper-title').setValue('Evidence study')
    await wrapper.get('#paper-abstract').setValue('Evidence from the supplied abstract.')
    await wrapper.get('#paper-authors').setValue('Alice, Bob\n陈研究员')
    await wrapper.get('#paper-categories').setValue('cs.AI，cs.IR')
    await wrapper.get('#paper-url').setValue('https://example.test/paper')
    await wrapper.get('[data-test="paper-import-form"]').trigger('submit')
    await flushPromises()
    expect(api.collections.addPaper).toHaveBeenCalledWith(7, expect.objectContaining({
      source: 'manual', paper_id: 'paper-1', authors: ['Alice', 'Bob', '陈研究员'],
      categories: ['cs.AI', 'cs.IR'], page_url: 'https://example.test/paper', pdf_url: null,
    }))
    wrapper.unmount()
  })

  it('rejects unsafe paper URLs before making a write request', async () => {
    const wrapper = await render(CollectionDetailView, '/collections/7')
    await wrapper.get('#paper-source').setValue('manual')
    await wrapper.get('#paper-id').setValue('paper-1')
    await wrapper.get('#paper-title').setValue('Evidence study')
    await wrapper.get('#paper-url').setValue('javascript:alert(1)')
    await wrapper.get('[data-test="paper-import-form"]').trigger('submit')
    await flushPromises()
    expect(api.collections.addPaper).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('HTTP 或 HTTPS')
    wrapper.unmount()
  })
})
