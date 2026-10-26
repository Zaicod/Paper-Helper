<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import type { Collection, PaperInput, SearchReport } from '../types'

defineProps<{ report: SearchReport }>()
const collections = ref<Collection[]>([]), target = ref(''), collectionError = ref(''), loading = ref(false)
const page = ref(0), total = ref(0), adding = ref(new Set<string>()), added = ref(new Set<string>())
const errors = ref<Record<string, string>>({})
let active = true
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败，请稍后重试。'
const identity = (paper: PaperInput, collection = target.value) => JSON.stringify([collection, paper.source, paper.paper_id])
const relevance = { match: '相关', uncertain: '待核实', background: '背景参考' }
const modality = { multimodal: '多模态', unimodal: '单模态', unknown: '模态待核实' }
const status = { ok: '已检索', empty: '无结果', unavailable: '来源不可用', timeout: '请求超时', rate_limited: '来源限流' }
function safeUrl(value?: string | null) {
  try { const url = new URL(value || ''); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null } catch { return null }
}
async function loadCollections() {
  if (loading.value) return
  loading.value = true; collectionError.value = ''
  try {
    const result = await api.collections.list('', page.value, 100)
    if (active) { collections.value.push(...result.collections); total.value = result.total; page.value++ }
  } catch (cause) { if (active) collectionError.value = message(cause) }
  finally { if (active) loading.value = false }
}
async function save(paper: PaperInput) {
  const collection = target.value, key = identity(paper, collection)
  if (!collections.value.some(item => String(item.id) === collection) || adding.value.has(key) || added.value.has(key)) return
  adding.value.add(key); delete errors.value[key]
  try { await api.collections.addPaper(Number(collection), paper); if (active) added.value.add(key) }
  catch (cause) { if (active) errors.value[key] = message(cause) }
  finally { if (active) adding.value.delete(key) }
}
onMounted(loadCollections)
onBeforeUnmount(() => { active = false })
</script>

<template>
  <section class="stack search-report" aria-label="智能搜索报告">
    <section class="panel stack">
      <div class="section-heading"><h2>智能搜索 · 问题分析</h2><span class="tag">{{ report.rounds }} 轮检索 · {{ report.results.length }} 篇结果</span></div>
      <p>{{ report.plan.summary }}</p>
      <div v-if="report.plan.concepts.length" class="actions" aria-label="研究概念"><span v-for="concept in report.plan.concepts" :key="concept" class="tag">{{ concept }}</span></div>
      <div v-if="report.plan.entities.length" class="entity-map"><p class="muted">{{ report.plan.entity_relation === 'any' ? '满足任一实体' : '同时满足全部实体' }}（依据论文标题与摘要）</p><ul><li v-for="entity in report.plan.entities" :key="entity.name"><strong>{{ entity.name }}</strong><span v-if="entity.aliases.length" class="muted"> · 别名 {{ entity.aliases.join(' / ') }}</span></li></ul></div>
      <ul v-if="report.plan.constraints.length" aria-label="搜索约束"><li v-for="constraint in report.plan.constraints" :key="constraint">{{ constraint }}</li></ul>
      <details><summary>查看搜索计划</summary><ul><li v-for="(query,index) in report.plan.queries" :key="index"><strong>{{ query.source }}</strong> · {{ query.keywords.map(keyword => `${keyword.text}（${keyword.match_mode === 'exact' ? '精确' : '宽泛'}）`).join(' / ') }}<p class="muted">{{ query.purpose }}</p></li></ul></details>
    </section>
    <section class="panel stack" aria-labelledby="search-trace-title">
      <h2 id="search-trace-title">实际检索记录</h2>
      <ol class="search-trace"><li v-for="(search,index) in report.searches" :key="index"><div class="actions"><span class="tag">第 {{ search.round }} 轮</span><strong>{{ search.source }}</strong><span>{{ status[search.status] }} · {{ search.count }} 篇</span></div><p class="query">{{ search.query }}</p></li></ol>
      <p v-if="!report.searches.length" class="muted">本次未产生检索记录。</p>
    </section>
    <section v-if="report.warnings.length || report.gaps.length" class="panel stack" aria-label="搜索限制与缺口">
      <h2>限制与待补充证据</h2><p v-for="(warning,index) in report.warnings" :key="`warning-${index}`" class="notice" role="status">{{ warning }}</p><ul v-if="report.gaps.length"><li v-for="(gap,index) in report.gaps" :key="index">{{ gap }}</li></ul>
    </section>
    <div class="section-heading"><h2>检索结果</h2><span class="muted">元数据相关性筛选</span></div>
    <p class="notice">匹配依据来自真实来源的标题与摘要。元数据相关性与模态判断仍需阅读全文核实，不能据此确认论文实际采用了某数据集进行实验。</p>
    <div v-if="!report.results.length" class="panel empty-state"><h3>没有找到可返回的论文</h3><p>结合上方检索记录与证据缺口，尝试补充数据集别名、模态或更明确的研究问题。</p><RouterLink class="button secondary" to="/papers">调整研究问题</RouterLink></div>
    <template v-else>
      <section class="panel stack">
        <label class="field" for="search-report-collection">保存到我的收藏夹<select id="search-report-collection" v-model="target" :disabled="adding.size > 0"><option value="">请选择收藏夹</option><option v-for="collection in collections" :key="collection.id" :value="String(collection.id)">{{ collection.name }}</option></select></label>
        <p v-if="collectionError" class="notice error" role="alert">{{ collectionError }} <button class="button secondary small" @click="loadCollections">重新读取</button></p>
        <p v-else-if="loading" class="muted" role="status">正在读取收藏夹…</p>
        <p v-else-if="!collections.length" class="muted">还没有收藏夹。<RouterLink to="/collections">新建收藏夹</RouterLink>后可保存论文。</p>
        <button v-if="collections.length < total" class="button secondary" :disabled="loading" @click="loadCollections">加载更多收藏夹</button>
      </section>
      <article v-for="result in report.results" :key="result.candidate_id" class="panel stack search-result">
        <div class="actions"><span class="tag">{{ relevance[result.relevance] }}</span><span class="tag">{{ modality[result.modality] }}</span><span class="muted">{{ result.paper.source }} · {{ result.paper.published || '发表日期未知' }}</span></div>
        <h3>{{ result.paper.title }}</h3><p class="muted">{{ result.paper.authors.join(' · ') || '未提供作者' }}</p>
        <p><strong>筛选理由：</strong>{{ result.reason }}</p>
        <p class="muted">实体匹配：{{ result.matched_entities.join(' / ') || '暂无可核实的实体匹配' }}</p>
        <div class="evidence"><h4>标题 / 摘要依据</h4><blockquote v-for="(evidence,index) in result.evidence" :key="index">{{ evidence }}</blockquote><p v-if="!result.evidence.length" class="muted">尚无可引用的匹配片段，需进一步核实。</p></div>
        <details><summary>阅读摘要与来源</summary><p class="abstract">{{ result.paper.abstract || '来源未提供摘要。' }}</p><ul><li v-for="(origin,index) in result.provenance" :key="index">{{ origin.source }} · {{ origin.query }}</li></ul><p class="muted">{{ result.paper.paper_id }}<span v-if="result.paper.cited_by_count != null"> · 来源引用数 {{ result.paper.cited_by_count }}</span></p></details>
        <div class="actions result-actions"><div class="actions"><a v-if="safeUrl(result.paper.page_url)" :href="safeUrl(result.paper.page_url)!" target="_blank" rel="noopener noreferrer">论文页面 ↗</a><a v-if="safeUrl(result.paper.pdf_url)" :href="safeUrl(result.paper.pdf_url)!" target="_blank" rel="noopener noreferrer">PDF ↗</a></div><button class="button secondary" data-test="save-search-result" :disabled="!target || adding.has(identity(result.paper)) || added.has(identity(result.paper))" @click="save(result.paper)">{{ adding.has(identity(result.paper)) ? '正在加入…' : added.has(identity(result.paper)) ? '已加入此收藏夹' : '加入收藏夹' }}</button></div>
        <p v-if="errors[identity(result.paper)]" class="notice error" role="alert">{{ errors[identity(result.paper)] }}</p>
      </article>
    </template>
  </section>
</template>

<style scoped>
.search-report h2,.search-report h3,.search-report h4,.search-report p,.search-report ul{margin:0}.search-report h3{font-size:19px}.search-report summary{cursor:pointer;color:var(--blue)}.search-trace{list-style:none;padding:0;margin:0}.search-trace li{border-left:2px solid var(--line);padding:4px 0 18px 16px;margin:0}.search-trace li:last-child{padding-bottom:4px}.query{font:12px Consolas,monospace;overflow-wrap:anywhere;padding-top:7px}.entity-map{background:var(--paper);border-radius:6px;padding:14px 16px}.evidence{border-left:3px solid var(--green);padding:4px 0 4px 16px}.evidence h4{font-size:12px;color:var(--green)}blockquote{margin:10px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}.abstract{white-space:pre-wrap;padding-top:14px;line-height:1.85}.result-actions{justify-content:space-between}.search-result{overflow-wrap:anywhere}.search-report .section-heading{margin-bottom:0}@media(max-width:650px){.result-actions{align-items:flex-start;flex-direction:column}.result-actions>button{width:100%}}
</style>
