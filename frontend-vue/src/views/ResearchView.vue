<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import type { TaskCategory, TaskPage, TaskStatus } from '../types'

const route = useRoute()
const router = useRouter()
const tabs: { key: TaskCategory; label: string; empty: string; hint: string }[] = [
  { key: 'active', label: '进行中', empty: '暂无进行中的研究', hint: '等待执行和正在研究的任务会显示在这里。' },
  { key: 'unfinished', label: '未完成', empty: '暂无未完成的研究', hint: '执行失败或中断的任务会保留在这里，可进入详情查看原因并重试。' },
  { key: 'history', label: '历史研究', empty: '暂无已完成的研究', hint: '研究完成后会自动归入历史记录，可随时查看和下载报告。' },
]
function scalar(value: unknown): string { return typeof value === 'string' ? value : '' }
const category = computed<TaskCategory>(() => tabs.find(t => t.key === route.query.category)?.key ?? 'active')
const keyword = computed(() => scalar(route.query.keyword).trim().slice(0, 500))
const page = computed(() => {
  const value = Number(scalar(route.query.page))
  return Number.isSafeInteger(value) && value > 0 && value <= 2147483648 ? value - 1 : 0
})
const currentTab = computed(() => tabs.find(t => t.key === category.value)!)
const data = ref<TaskPage | null>(null)
const loading = ref(false)
const error = ref('')
const draft = ref('')
let requestVersion = 0
const statusLabel: Record<TaskStatus, string> = { queued: '等待执行', running: '正在研究', completed: '已完成', failed: '执行失败', interrupted: '已中断' }
const totalPages = computed(() => Math.max(1, Math.ceil((data.value?.total ?? 0) / 10)))
async function navigate(nextCategory: TaskCategory, nextKeyword: string, nextPage = 0) {
  await router.push({ path: '/research', query: { category: nextCategory, ...(nextKeyword ? { keyword: nextKeyword } : {}), page: String(nextPage + 1) } })
}
async function load() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  data.value = null
  try {
    const result = await api.tasks.list(page.value, 10, category.value, keyword.value)
    if (version !== requestVersion) return
    const lastPage = Math.max(0, Math.ceil(result.total / 10) - 1)
    if (page.value > lastPage) {
      await router.replace({ path: '/research', query: { category: category.value, ...(keyword.value ? { keyword: keyword.value } : {}), page: String(lastPage + 1) } })
      return
    }
    data.value = result
  } catch (cause) {
    if (version === requestVersion) error.value = cause instanceof Error ? cause.message : '任务列表读取失败，请重试。'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
async function search() {
  const term = draft.value.trim()
  if (keyword.value === term && page.value === 0) await load()
  else await navigate(category.value, term)
}
async function clearSearch() {
  draft.value = ''
  if (!keyword.value && page.value === 0) await load()
  else await navigate(category.value, '')
}
function tabKey(event: KeyboardEvent, index: number) {
  const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
  const target = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : offset ? (index + offset + tabs.length) % tabs.length : -1
  if (target < 0) return
  event.preventDefault()
  const tab = tabs[target]!
  document.getElementById(`tab-${tab.key}`)?.focus()
  void navigate(tab.key, keyword.value)
}
function date(value: string) { return new Date(value).toLocaleString('zh-CN') }
watch([category, keyword, page], () => { draft.value = keyword.value; void load() }, { immediate: true })
onBeforeUnmount(() => { requestVersion++ })
</script>

<template>
  <section class="stack">
    <div class="page-heading"><div><p class="eyebrow">RESEARCH / 研究记录</p><h1>研究任务</h1><p class="muted">追踪当前进度，处理未完成任务，回顾已完成的研究。</p></div><RouterLink class="button primary" to="/research/new">新建研究</RouterLink></div>
    <div class="panel research-controls">
      <div class="research-tabs" role="tablist" aria-label="研究任务分类">
        <button v-for="(tab, index) in tabs" :id="`tab-${tab.key}`" :key="tab.key" type="button" role="tab" :data-test="`tab-${tab.key}`" :aria-selected="category === tab.key" aria-controls="research-results" :tabindex="category === tab.key ? 0 : -1" @click="navigate(tab.key, keyword)" @keydown="tabKey($event, index)">{{ tab.label }}</button>
      </div>
      <form class="research-search" role="search" @submit.prevent="search">
        <label class="search-field">搜索研究主题<input v-model="draft" type="search" maxlength="500" placeholder="输入研究主题关键词" /></label>
        <button class="button primary" type="submit">搜索</button>
        <button v-if="draft || keyword" class="button secondary" type="button" data-test="clear-search" @click="clearSearch">清空</button>
        <button class="button secondary" type="button" data-test="refresh-tasks" :disabled="loading" @click="load">刷新列表</button>
      </form>
    </div>
    <div id="research-results" class="stack" role="tabpanel" :aria-labelledby="`tab-${category}`" :aria-busy="loading" tabindex="0">
      <div class="list-caption"><h2>{{ currentTab.label }}</h2><span v-if="data" class="muted">共 {{ data.total }} 条 · 每页 10 条</span></div>
      <div v-if="error" class="notice error" role="alert">{{ error }} <button class="button secondary small" data-test="retry-list" @click="load">重新读取</button></div>
      <p v-if="loading" class="muted" role="status">正在读取研究任务…</p>
      <div v-if="data?.tasks.length" class="panel task-list">
        <RouterLink v-for="task in data.tasks" :key="task.task_id" class="task-row" :to="{ path: `/research/${task.task_id}`, query: { category, ...(keyword ? { keyword } : {}), page: String(page + 1) } }">
          <div><span class="tag">{{ task.task_type === 'study_report' ? '学习报告' : '研究分析' }}</span><h2>{{ task.topic }}</h2><p class="muted">创建于 {{ date(task.created_at) }}</p></div>
          <span class="tag" :data-status="task.status">{{ statusLabel[task.status] }}</span><span class="arrow" aria-hidden="true">↗</span>
        </RouterLink>
      </div>
      <div v-else-if="data && !loading && !error" class="panel empty-state"><h2>{{ keyword ? '没有匹配的研究记录' : currentTab.empty }}</h2><p>{{ keyword ? '试试其他关键词，或清空搜索查看当前分类的全部记录。' : currentTab.hint }}</p><RouterLink v-if="!keyword" class="button primary" to="/research/new">新建研究</RouterLink></div>
      <nav v-if="data && data.total > 0" class="actions research-pagination" aria-label="研究任务分页"><button class="button secondary" data-test="previous-page" :disabled="loading || page === 0" @click="navigate(category, keyword, page - 1)">上一页</button><span class="muted">第 {{ page + 1 }} / {{ totalPages }} 页 · 共 {{ data.total }} 条</span><button class="button secondary" data-test="next-page" :disabled="loading || page + 1 >= totalPages" @click="navigate(category, keyword, page + 1)">下一页</button></nav>
    </div>
  </section>
</template>

<style scoped>
.research-controls { padding: 0 24px 24px; }
.research-tabs { display: flex; gap: 28px; border-bottom: 1px solid var(--line); margin-bottom: 22px; }
.research-tabs button { border: 0; border-bottom: 3px solid transparent; background: transparent; padding: 17px 2px 14px; color: var(--muted); white-space: nowrap; }
.research-tabs button[aria-selected="true"] { border-bottom-color: var(--blue); color: var(--blue); font-weight: 650; }
.research-search { display: flex; align-items: flex-end; gap: 10px; flex-wrap: wrap; }
.search-field { flex: 1 1 250px; display: grid; gap: 7px; font-size: 13px; }
.list-caption { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.list-caption h2 { font-size: 18px; margin: 0; }
.task-list { padding: 0; overflow: hidden; }
.task-row { display: grid; grid-template-columns: minmax(0,1fr) auto 20px; align-items: center; gap: 18px; padding: 24px; color: inherit; text-decoration: none; border-bottom: 1px solid var(--line); }
.task-row:last-child { border-bottom: 0; }.task-row:hover { background: var(--paper); text-decoration: none; }
.task-row h2 { font-size: 17px; margin: 0 0 8px; overflow-wrap: anywhere; }.task-row p { margin: 0; font-size: 13px; }.arrow { color: var(--blue); }
[data-status="completed"] { color: var(--green); }[data-status="failed"],[data-status="interrupted"] { color: #a43c35; }
.research-pagination { justify-content: center; }
@media (max-width: 560px) { .research-controls { padding: 0 16px 16px; }.research-tabs { gap: 24px; }.search-field { flex-basis: 100%; }.task-row { padding: 18px; gap: 10px; grid-template-columns: minmax(0,1fr) auto; }.arrow { display:none; } }
</style>
