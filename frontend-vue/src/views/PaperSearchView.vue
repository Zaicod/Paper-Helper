<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { useSearchDraft } from '../composables/searchDraft'
import type { Collection, PaperInput, PaperSearchResult, PaperSource, PaperSort, SearchKeyword } from '../types'

const query = ref(''), source = ref<PaperSource>('auto'), limit = ref(10)
const keywords = ref<SearchKeyword[]>([]), keywordMode = ref<SearchKeyword['match_mode']>('fuzzy'), composing = ref(false)
const effectiveKeywords = computed(() => {
  const terms = keywords.value.map(item => ({ ...item }))
  const text = query.value.trim()
  if (text && !terms.some(item => item.text.toLowerCase() === text.toLowerCase())) terms.push({ text, match_mode: keywordMode.value })
  return terms
})
const hasExact = computed(() => effectiveKeywords.value.some(item => item.match_mode === 'exact'))
const hasChinese = computed(() => /[\u3400-\u9fff]/.test(effectiveKeywords.value.map(item => item.text).join(' ')))
const sort = ref<PaperSort>('relevance'), submittedFilters = ref('')
const filterKey = computed(() => JSON.stringify([keywords.value, query.value.trim(), query.value.trim() ? keywordMode.value : null, source.value, limit.value, sort.value]))
const canPage = computed(() => !searching.value && submittedFilters.value === filterKey.value)
watch(source, value => { if (value === 'arxiv' && sort.value === 'citations') sort.value = 'relevance' })
const auth = useAuthStore()
const { unavailable: draftUnavailable } = useSearchDraft(computed(() => auth.user?.id ?? null), { query, keywords, keywordMode, source, sort, limit })
const result = ref<PaperSearchResult | null>(null)
const searching = ref(false), error = ref(''), collectionError = ref('')
const collections = ref<Collection[]>([]), target = ref(''), collectionPage = ref(0), collectionTotal = ref(0), loadingCollections = ref(false)
const adding = ref(new Set<string>()), added = ref(new Set<string>())
const addErrors = ref<Record<string, string>>({})
const anyAdding = computed(() => adding.value.size > 0)
let generation = 0, active = true
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作未能完成，请稍后重试。'
const identity = (paper: PaperInput, collection = target.value) => JSON.stringify([collection, paper.source, paper.paper_id])
function safeUrl(value?: string | null) {
  try { const url = new URL(value || ''); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null } catch { return null }
}
function keywordError(terms: SearchKeyword[]) {
  if (!terms.length) return '请至少输入一个检索关键词。'
  if (terms.length > 10) return '最多 10 个关键词，请移除部分关键词后重试。'
  if (terms.map(item => item.text).join(' / ').length > 500) return '关键词与分隔符总长度不能超过 500 字。'
  return ''
}
function addKeyword() {
  if (!query.value.trim()) return
  if (keywords.value.some(item => item.text.toLowerCase() === query.value.trim().toLowerCase())) {
    error.value = '关键词已存在，保留原有匹配方式。请移除原关键词后重新添加，或输入其他关键词。'
    return
  }
  const validation = keywordError(effectiveKeywords.value)
  if (validation) { error.value = validation; return }
  keywords.value = effectiveKeywords.value
  query.value = ''
  error.value = ''
}
function keywordEnter(event: KeyboardEvent) {
  if (event.key !== 'Enter') return
  event.preventDefault()
  if (event.isComposing || composing.value || event.keyCode === 229) return
  addKeyword()
}
function removeKeyword(index: number) { keywords.value = keywords.value.filter((_, position) => position !== index); error.value = '' }
function clearKeywords() { keywords.value = []; query.value = ''; error.value = '' }
async function loadCollections() {
  if (loadingCollections.value) return
  loadingCollections.value = true; collectionError.value = ''
  try {
    const page = await api.collections.list('', collectionPage.value, 100)
    if (!active) return
    collections.value.push(...page.collections); collectionTotal.value = page.total; collectionPage.value++
  } catch (cause) { if (active) collectionError.value = message(cause) }
  finally { if (active) loadingCollections.value = false }
}
async function search(page = 1, navigation = false) {
  if (searching.value) return
  error.value = ''
  const validation = keywordError(effectiveKeywords.value)
  if (validation) { error.value = validation; return }
  if (source.value === 'crossref' && hasExact.value) { error.value = 'Crossref 不支持精确短语，请改选 arXiv / OpenAlex，或移除精确关键词后重新添加宽泛匹配。'; return }
  if (!Number.isInteger(Number(limit.value)) || Number(limit.value) < 1 || Number(limit.value) > 20) { error.value = '结果数量应为 1 至 20 的整数。'; return }
  if (navigation && !canPage.value) return
  if (!navigation) { keywords.value = effectiveKeywords.value; query.value = '' }
  const terms = keywords.value.map(item => ({ ...item }))
  const keyword = terms.map(item => item.text).join(' / ')
  const current = ++generation
  const filters = filterKey.value
  const requestedSource = navigation ? result.value?.used_source as PaperSource : source.value
  searching.value = true
  try {
    const response = await api.papers.search(keyword, requestedSource, Number(limit.value), page, sort.value, terms)
    if (current === generation && active) { result.value = response; submittedFilters.value = filters }
  } catch (cause) { if (current === generation && active) error.value = message(cause) }
  finally { if (current === generation && active) searching.value = false }
}
async function add(paper: PaperInput) {
  const currentTarget = target.value, key = identity(paper, currentTarget)
  if (!collections.value.some(item => String(item.id) === currentTarget) || adding.value.has(key) || added.value.has(key)) return
  adding.value.add(key); delete addErrors.value[key]
  try {
    await api.collections.addPaper(Number(currentTarget), paper)
    if (active) added.value.add(key)
  } catch (cause) { if (active) addErrors.value[key] = message(cause) }
  finally { if (active) adding.value.delete(key) }
}
onMounted(loadCollections)
onBeforeUnmount(() => { active = false; generation++ })
</script>

<template>
  <section class="stack search-page">
    <header class="page-heading"><div><p class="eyebrow">FIND YOUR EVIDENCE</p><h1>搜索论文</h1><p class="muted">从 arXiv、OpenAlex 与 Crossref 检索真实文献，加入自己的研究资料库。</p></div><RouterLink class="button secondary" to="/collections">管理收藏夹</RouterLink></header>
    <form class="panel stack" data-test="paper-search-form" @submit.prevent="search()">
      <fieldset class="stack" :disabled="searching">
        <label class="field" for="paper-query">检索关键词<input id="paper-query" v-model="query" class="input" maxlength="500" placeholder="输入一个关键词或完整短语，不会按空格拆分" @keydown="keywordEnter" @compositionstart="composing = true" @compositionend="composing = false"></label>
        <div class="keyword-editor actions"><label class="field" for="keyword-mode">新关键词匹配方式<select id="keyword-mode" v-model="keywordMode"><option value="fuzzy">模糊匹配</option><option value="exact">精准匹配</option></select></label><button type="button" class="button secondary" data-test="add-keyword" @click="addKeyword">添加关键词</button><button type="button" class="button secondary small" data-test="clear-keywords" :disabled="!keywords.length && !query.trim()" @click="clearKeywords">清空关键词</button><span class="muted">已添加 {{ keywords.length }} / 10</span></div>
        <ul v-if="keywords.length" class="keyword-list" aria-label="已添加的关键词"><li v-for="(keyword,index) in keywords" :key="keyword.text.toLowerCase()" class="keyword-chip" data-test="keyword-chip"><span>{{ keyword.text }}</span><small>{{ keyword.match_mode === 'exact' ? '精准匹配' : '模糊匹配' }}</small><button type="button" :aria-label="`移除关键词：${keyword.text}`" @click="removeKeyword(index)">×</button></li></ul>
        <p class="muted keyword-help">输入后按 Enter 或添加，可逐个移除。arXiv / OpenAlex 的多个关键词按 AND 组合；精准匹配搜索完整连续短语，模糊匹配使用宽泛的普通词搜索，不自动翻译。搜索时也会加入输入框中尚未添加的关键词。</p>
        <div class="form-grid"><label class="field" for="search-source">文献来源<select id="search-source" v-model="source"><option value="auto">自动选择真实来源</option><option value="arxiv">arXiv</option><option value="openalex">OpenAlex</option><option value="crossref" :disabled="hasExact">Crossref（宽泛搜索）</option></select></label><label class="field" for="search-limit">每页数量<select id="search-limit" v-model.number="limit"><option :value="10">10 篇</option><option :value="20">20 篇</option></select></label><label class="field" for="search-sort">排序方式<select id="search-sort" v-model="sort"><option value="relevance">最相关</option><option value="latest">最新发表</option><option value="citations" :disabled="source === 'arxiv'">引用最多（OpenAlex / Crossref）</option></select><span class="muted">arXiv 不提供引用排序；自动引用排序优先 OpenAlex，全部为宽泛关键词时可回退 Crossref。</span></label></div>
      </fieldset>
      <p v-if="hasChinese" class="notice">中文关键词会按原文检索，暂不自动翻译。可尝试英文关键词，例如“多模态” → multimodal 或 multimodal learning。</p>
      <p v-if="draftUnavailable" class="notice" role="status">当前浏览器无法保存搜索条件，切换页面后可能需要重新输入。</p>
      <div class="actions"><button class="button primary" :disabled="searching">{{ searching ? '正在检索文献…' : '搜索论文' }}</button><span class="muted">外部来源可能需要数秒；自动模式不会返回演示数据。</span></div>
    </form>
    <p v-if="error" class="notice error" role="alert">{{ error }}<span v-if="result"> 下方保留上一次成功检索的结果。</span></p>
    <section class="panel stack" aria-labelledby="save-destination">
      <div class="section-heading"><h2 id="save-destination">保存到我的收藏夹</h2><RouterLink to="/collections">新建收藏夹 ↗</RouterLink></div>
      <label class="field" for="target-collection">目标收藏夹<select id="target-collection" v-model="target" :disabled="anyAdding"><option value="">请选择收藏夹</option><option v-for="item in collections" :key="item.id" :value="String(item.id)">{{ item.name }}</option></select></label>
      <p v-if="collectionError" class="notice error" role="alert">{{ collectionError }} <button class="button secondary small" :disabled="loadingCollections" @click="loadCollections">重新读取收藏夹</button></p>
      <p v-else-if="loadingCollections" class="muted" role="status">正在读取收藏夹…</p>
      <p v-else-if="!collections.length" class="muted">还没有收藏夹。先前往资料库新建一个，再搜索和收藏论文。</p>
      <button v-if="collections.length < collectionTotal" class="button secondary small more-collections" :disabled="loadingCollections" @click="loadCollections">{{ loadingCollections ? '正在读取…' : `加载更多收藏夹（已显示 ${collections.length} / ${collectionTotal}）` }}</button>
      <p class="muted save-help">重复添加会保留原有个人笔记和已编辑的论文资料。</p>
    </section>
    <template v-if="result">
      <p v-if="result.used_source === 'crossref'" class="notice">Crossref 使用宽泛相关性搜索，不保证全部关键词同时出现，也不支持精确短语或布尔 AND。引用数仅覆盖 Crossref 记录的 DOI 引用，不能与其他来源直接等同比较；部分论文可能缺少摘要或开放 PDF。</p>
      <p v-for="warning in result.warnings ?? []" :key="`${warning.source}-${warning.code}`" class="notice" role="status">{{ warning.message }}</p>
      <div class="section-heading"><div><h2>检索结果</h2><p class="muted">“{{ result.query }}” · 实际来源 {{ result.used_source }} · 本页 {{ result.papers.length }} 篇<span v-if="result.total !== undefined"> · 共 {{ result.total }} 篇匹配</span></p></div></div>
      <div v-if="result.page" class="actions" aria-label="搜索分页"><button class="button secondary" :disabled="!canPage || result.page <= 1" @click="search(result.page - 1, true)">上一页</button><span>第 {{ result.page }} 页</span><button class="button secondary" data-test="next-page" :disabled="!canPage || !result.has_next" @click="search(result.page + 1, true)">下一页</button><span v-if="result.total && result.total > 10000" class="muted">当前支持浏览前 10000 条匹配。</span><span v-if="submittedFilters !== filterKey" class="muted">条件已修改，请重新搜索。</span></div>
      <div v-if="!result.papers.length" class="panel empty-state"><h3>没有找到匹配的论文</h3><p>试试其他关键词或切换文献来源。</p></div>
      <article v-for="paper in result.papers" :key="JSON.stringify([paper.source,paper.paper_id])" class="panel stack search-result">
        <div class="actions"><span class="tag">{{ paper.source }}</span><span class="muted paper-id">{{ paper.paper_id }}</span><span v-if="paper.published" class="muted">{{ paper.published }}</span><span class="muted">{{ paper.cited_by_count == null ? '暂无引用数据' : `引用 ${paper.cited_by_count} 次` }}</span></div>
        <h3>{{ paper.title }}</h3><p class="muted">{{ paper.authors.join(' · ') || '未提供作者' }}</p>
        <details><summary>阅读摘要与论文资料</summary><p class="abstract">{{ paper.abstract || '该来源未提供摘要。' }}</p><p v-if="paper.categories.length" class="muted">分类：{{ paper.categories.join(' / ') }}</p></details>
        <div class="actions result-actions"><div class="actions"><a v-if="safeUrl(paper.page_url)" :href="safeUrl(paper.page_url)!" target="_blank" rel="noopener noreferrer">论文页面 ↗</a><a v-if="safeUrl(paper.pdf_url)" :href="safeUrl(paper.pdf_url)!" target="_blank" rel="noopener noreferrer">PDF ↗</a></div><button class="button secondary" data-test="add-search-paper" :disabled="!target || adding.has(identity(paper)) || added.has(identity(paper))" @click="add(paper)">{{ adding.has(identity(paper)) ? '正在加入…' : added.has(identity(paper)) ? '已加入此收藏夹' : '加入收藏夹' }}</button></div>
        <p v-if="addErrors[identity(paper)]" class="notice error" role="alert">{{ addErrors[identity(paper)] }}</p><p v-if="added.has(identity(paper))" class="notice success" role="status">已保存到选中的收藏夹。可在资料库中整理阅读笔记。</p>
      </article>
    </template>
    <div v-else-if="!searching" class="empty-state"><h2>从一条可核查的文献开始</h2><p>输入研究问题或英文关键词，检索后选择需要保存的论文。</p></div>
  </section>
</template>

<style scoped>
.keyword-editor{align-items:flex-end}.keyword-editor .field{min-width:160px}.keyword-list{display:flex;flex-wrap:wrap;gap:10px;list-style:none;padding:0;margin:0}.keyword-chip{display:flex;align-items:center;gap:10px;border:1px solid #dae3ef;border-radius:8px;padding:8px 12px;max-width:100%;background:#f4f7fb}.keyword-chip>span{overflow-wrap:anywhere;min-width:0}.keyword-chip small{color:#677a92;font-size:11px;white-space:nowrap}.keyword-chip button{border:0;background:transparent;color:#245bea;font-size:20px;cursor:pointer;flex-shrink:0}.keyword-help{font-size:13px;line-height:1.7;margin:0}fieldset{border:0;padding:0;margin:0;min-width:0}.search-result h3{font-size:1.2rem;line-height:1.65;margin:0;overflow-wrap:anywhere}.search-result p{margin:0;overflow-wrap:anywhere}.search-result summary{cursor:pointer;color:#245bea}.abstract{white-space:pre-wrap;line-height:1.85;padding-top:16px}.paper-id{font:12px ui-monospace,monospace;overflow-wrap:anywhere}.result-actions{justify-content:space-between}.result-actions a{font-size:.86rem;color:#245bea}.save-help{font-size:.82rem;margin:0}.more-collections{width:fit-content}.search-page> .panel{min-width:0}.search-result details{min-width:0}.search-page .section-heading h2{margin:0}@media(max-width:650px){.result-actions{align-items:flex-start;flex-direction:column}.result-actions>button{width:100%}}
</style>
