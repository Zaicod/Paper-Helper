<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import type { Collection } from '../types'

const collections = ref<Collection[]>([])
const total = ref(0)
const page = ref(0)
const size = 12
const search = ref('')
const appliedSearch = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')
const editing = ref<number | null>(null)
const name = ref('')
const description = ref('')
const pages = computed(() => Math.max(1, Math.ceil(total.value / size)))
let requestNumber = 0

function message(cause: unknown) {
  return cause instanceof Error ? cause.message : '操作未完成，请稍后重试。'
}

async function load() {
  const request = ++requestNumber
  loading.value = true
  try {
    const result = await api.collections.list(appliedSearch.value, page.value, size)
    if (request !== requestNumber) return
    collections.value = result.collections
    total.value = result.total
  } catch (cause) {
    if (request === requestNumber) error.value = message(cause)
  } finally {
    if (request === requestNumber) loading.value = false
  }
}

async function find() {
  appliedSearch.value = search.value.trim()
  page.value = 0
  error.value = ''
  await load()
}

async function changePage(next: number) {
  if (loading.value || next < 0 || next >= pages.value) return
  page.value = next
  error.value = ''
  await load()
}

function edit(collection: Collection) {
  editing.value = collection.id
  name.value = collection.name
  description.value = collection.description
  error.value = ''
  success.value = ''
  document.getElementById('collection-name')?.focus()
}

function resetForm() {
  editing.value = null
  name.value = ''
  description.value = ''
}

async function save() {
  if (saving.value) return
  error.value = ''
  success.value = ''
  if (!name.value.trim()) {
    error.value = '请填写收藏夹名称。'
    return
  }
  saving.value = true
  try {
    const input = { name: name.value.trim(), description: description.value }
    if (editing.value === null) await api.collections.create(input)
    else await api.collections.update(editing.value, input)
    success.value = editing.value === null ? '收藏夹已创建。' : '收藏夹信息已保存。'
    resetForm()
    await load()
  } catch (cause) {
    error.value = message(cause)
  } finally {
    saving.value = false
  }
}

async function remove(collection: Collection) {
  if (saving.value || !window.confirm(`确定删除「${collection.name}」及其中的个人笔记？已提交的研究任务历史会保留。`)) return
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    await api.collections.remove(collection.id)
    if (editing.value === collection.id) resetForm()
    if (collections.value.length === 1 && page.value > 0) page.value--
    success.value = '收藏夹已删除。'
    await load()
  } catch (cause) {
    error.value = message(cause)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="stack collections-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">YOUR RESEARCH LIBRARY</p>
        <h1>收藏夹</h1>
        <p class="muted">把论文与阅读笔记放在一起，逐步积累自己的研究证据。</p>
      </div>
      <span class="library-total" aria-label="收藏夹总数">{{ total }} <small>个收藏夹</small></span>
    </header>

    <p v-if="error" role="alert" class="notice error">{{ error }}</p>
    <p v-if="success" role="status" class="notice success">{{ success }}</p>

    <div class="library-layout">
      <section class="panel library-content" aria-labelledby="library-list-heading">
        <div class="section-heading">
          <h2 id="library-list-heading">我的收藏夹</h2>
          <span class="muted">仅当前账号可见</span>
        </div>
        <form class="search-form" role="search" @submit.prevent="find">
          <label class="search-label" for="collection-search">搜索名称或描述</label>
          <div class="search-controls">
            <input id="collection-search" v-model="search" class="input" maxlength="255" placeholder="搜索你的研究主题" type="search" />
            <button class="button secondary" :disabled="loading">搜索</button>
          </div>
        </form>

        <p v-if="loading" class="muted" role="status">正在读取收藏夹…</p>
        <div v-else-if="collections.length === 0" class="empty-state">
          <h3>{{ appliedSearch ? '没有找到匹配的收藏夹' : '从一个研究问题开始' }}</h3>
          <p>{{ appliedSearch ? '试试其他关键词，或清空搜索查看全部。' : '新建收藏夹后，可以录入论文、整理笔记，再交给 Agent 研究。' }}</p>
        </div>
        <ul v-else class="collection-list">
          <li v-for="collection in collections" :key="collection.id" class="list-row collection-row">
            <div class="collection-copy">
              <span class="tag">{{ collection.paper_count }} 篇论文</span>
              <h3><RouterLink :to="`/collections/${collection.id}`">{{ collection.name }}</RouterLink></h3>
              <p class="muted">{{ collection.description || '暂未填写描述' }}</p>
            </div>
            <div class="actions row-actions">
              <RouterLink class="button secondary small" :to="`/collections/${collection.id}`">打开</RouterLink>
              <button class="button secondary small" :disabled="saving" @click="edit(collection)">编辑</button>
              <button class="button danger small" data-test="delete-collection" :disabled="saving" :aria-label="`删除收藏夹：${collection.name}`" @click="remove(collection)">删除</button>
            </div>
          </li>
        </ul>
        <nav v-if="total > 0" class="pagination" aria-label="收藏夹分页">
          <button class="button secondary small" :disabled="loading || page === 0" @click="changePage(page - 1)">上一页</button>
          <span class="muted" aria-live="polite">第 {{ page + 1 }} / {{ pages }} 页</span>
          <button class="button secondary small" :disabled="loading || page + 1 >= pages" @click="changePage(page + 1)">下一页</button>
        </nav>
      </section>

      <section class="panel collection-editor" aria-labelledby="collection-form-heading">
        <p class="eyebrow">ORGANIZE YOUR EVIDENCE</p>
        <h2 id="collection-form-heading">{{ editing === null ? '新建收藏夹' : '编辑收藏夹' }}</h2>
        <form class="stack" data-test="collection-form" @submit.prevent="save">
          <div class="field">
            <label class="label" for="collection-name">收藏夹名称 <span aria-hidden="true">*</span></label>
            <input id="collection-name" v-model="name" class="input" required maxlength="255" placeholder="例如：检索增强 Agent" :disabled="saving" />
          </div>
          <div class="field">
            <label class="label" for="collection-description">描述</label>
            <textarea id="collection-description" v-model="description" class="textarea" rows="4" maxlength="2000" placeholder="记录研究范围或想回答的问题" :disabled="saving" />
          </div>
          <div class="actions">
            <button class="button primary" :disabled="saving">{{ saving ? '正在保存…' : editing === null ? '创建收藏夹' : '保存修改' }}</button>
            <button v-if="editing !== null" type="button" class="button secondary" :disabled="saving" @click="resetForm">取消编辑</button>
          </div>
        </form>
      </section>
    </div>
  </div>
</template>

<style scoped>
.library-total { font-size: 2.25rem; font-weight: 650; white-space: nowrap; }
.library-total small { font-size: .8rem; font-weight: 400; color: var(--muted, #64748b); }
.library-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(250px, 320px); gap: 24px; align-items: start; }
.collection-editor h2 { margin-top: 0; }
.collection-editor { position: sticky; top: 24px; }
.search-form { margin: 20px 0; }
.search-label { display: block; margin-bottom: 8px; font-size: .85rem; font-weight: 600; }
.search-controls { display: flex; gap: 8px; }
.search-controls .input { min-width: 0; flex: 1; }
.collection-list { list-style: none; padding: 0; margin: 0; }
.collection-row { display: flex; gap: 20px; justify-content: space-between; align-items: center; padding: 24px 0; }
.collection-copy { min-width: 0; }
.collection-copy h3 { margin: 10px 0 7px; overflow-wrap: anywhere; font-size: 1.1rem; }
.collection-copy h3 a { text-decoration: none; color: inherit; }
.collection-copy h3 a:hover { color: #245bea; text-decoration: underline; }
.collection-copy p { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.row-actions { flex-shrink: 0; }
.pagination { display: flex; gap: 12px; justify-content: space-between; align-items: center; padding-top: 20px; }
@media (max-width: 1100px) { .library-layout { grid-template-columns: minmax(0, 1fr); } .collection-editor { position: static; } }
@media (max-width: 650px) { .collection-row { align-items: flex-start; flex-direction: column; gap: 14px; } .library-total { font-size: 1.6rem; } .pagination { gap: 6px; font-size: .8rem; } }
</style>
