<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import type { CitationReport, Collection, PaperInput } from '../types'

defineProps<{ report: CitationReport }>()
const auth = useAuthStore()
const owner = computed(() => auth.user?.id)
const collections = ref<Collection[]>([]), target = ref(''), loading = ref(false), collectionError = ref('')
const page = ref(0), total = ref(0), adding = ref(new Set<string>()), added = ref(new Set<string>())
const errors = ref<Record<string, string>>({})
let active = true, generation = 0
const relevance = {match:'相关',uncertain:'待核实',background:'背景参考'}
const direction = {both:'双向追踪',references:'参考文献',citations:'引用该论文的研究'}
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败，请稍后重试。'
const identity = (paper: PaperInput, collection = target.value) => JSON.stringify([collection,paper.source,paper.paper_id])
function safeUrl(value?: string | null) {
 try {const url=new URL(value || '');return ['http:','https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null} catch {return null}
}
async function loadCollections() {
 if(loading.value)return
 const token=generation, account=owner.value
 loading.value=true;collectionError.value=''
 try {const result=await api.collections.list('',page.value,100);if(active && generation===token && owner.value===account){collections.value.push(...result.collections);total.value=result.total;page.value++}}
 catch(cause){if(active && generation===token)collectionError.value=message(cause)}
 finally{if(active && generation===token)loading.value=false}
}
async function save(paper:PaperInput){
 const collection=target.value,key=identity(paper,collection),token=generation,account=owner.value
 if(!collections.value.some(item=>String(item.id)===collection)||adding.value.has(key)||added.value.has(key))return
 adding.value.add(key);delete errors.value[key]
 try{await api.collections.addPaper(Number(collection),paper);if(active && generation===token && owner.value===account)added.value.add(key)}
 catch(cause){if(active && generation===token)errors.value[key]=message(cause)}
 finally{if(active && generation===token)adding.value.delete(key)}
}
watch(owner,()=>{generation++;collections.value=[];target.value='';page.value=0;total.value=0;adding.value.clear();added.value.clear();errors.value={};loading.value=false;collectionError.value='';void loadCollections()},{flush:'sync'})
onMounted(loadCollections)
onBeforeUnmount(()=>{active=false;generation++})
</script>

<template>
 <section class="stack citation-report" aria-label="引用追踪报告">
  <section class="panel stack">
   <div class="section-heading"><h2>引用追踪 · 发现路径</h2><span class="tag">{{ direction[report.direction] }} · 一层关系 · {{ report.results.length }} 篇结果</span></div>
   <p class="muted">从以下种子论文出发，沿真实引用关系发现研究。</p>
   <ul class="seed-list"><li v-for="seed in report.seeds" :key="`${seed.source}:${seed.paper_id}`"><strong>{{ seed.title }}</strong><span class="muted"> · {{ seed.paper_id }}</span></li></ul>
   <p class="notice">引用关系不代表支持论文结论。相关性依据来自标题与摘要，不能据此确认实际实验或性能；阅读全文前仍需核实。</p>
  </section>
  <section v-if="report.warnings.length || report.gaps.length" class="panel stack" aria-label="追踪限制与缺口"><h2>限制与待核实内容</h2><p v-for="(warning,index) in report.warnings" :key="index" class="notice" role="status">{{ warning }}</p><ul><li v-for="(gap,index) in report.gaps" :key="index">{{ gap }}</li></ul></section>
  <div v-if="!report.results.length" class="panel empty-state"><h3>本次没有可返回的相关论文</h3><p>请结合上方限制调整种子论文或研究方向。没有结果不代表不存在相关研究。</p><RouterLink class="button secondary" to="/collections">选择其他种子论文</RouterLink></div>
  <template v-else>
   <section class="panel stack"><label class="field" for="citation-report-collection">保存到我的收藏夹<select id="citation-report-collection" v-model="target" :disabled="adding.size > 0"><option value="">请选择收藏夹</option><option v-for="collection in collections" :key="collection.id" :value="String(collection.id)">{{ collection.name }}</option></select></label><p v-if="collectionError" class="notice error" role="alert">{{ collectionError }} <button class="button secondary small" @click="loadCollections">重新读取</button></p><p v-else-if="loading" class="muted">正在读取收藏夹…</p><p v-else-if="!collections.length" class="muted">还没有收藏夹。<RouterLink to="/collections">新建收藏夹</RouterLink>后可保存论文。</p><button v-if="collections.length < total" class="button secondary" :disabled="loading" @click="loadCollections">加载更多收藏夹</button></section>
   <article v-for="result in report.results" :key="result.candidate_id" class="panel stack citation-result">
    <div class="actions"><span class="tag">{{ relevance[result.relevance] }}</span><span class="muted">{{ result.paper.source }} · {{ result.paper.published || '发表日期未知' }}</span></div>
    <h3>{{ result.paper.title }}</h3><p class="muted">{{ result.paper.authors.join(' · ') || '来源未提供作者' }}</p>
    <ul class="citation-paths" aria-label="发现路径"><li v-for="(path,index) in result.paths" :key="index"><strong>{{ path.direction === 'references' ? '参考文献：种子论文引用了这篇论文' : '后续研究：这篇论文引用了种子论文' }}</strong><p>{{ path.seed_title }}</p><small class="muted">{{ path.from_id }} → {{ path.to_id }}</small></li></ul>
    <p><strong>筛选理由：</strong>{{ result.reason }}</p><div class="evidence"><strong>标题 / 摘要依据</strong><blockquote v-for="(evidence,index) in result.evidence" :key="index">{{ evidence }}</blockquote><p v-if="!result.evidence.length" class="muted">缺少足够匹配片段，需进一步核实。</p></div>
    <details><summary>阅读摘要</summary><p class="abstract">{{ result.paper.abstract || '来源未提供摘要。' }}</p></details>
    <div class="actions result-actions"><div class="actions"><a v-if="safeUrl(result.paper.page_url)" :href="safeUrl(result.paper.page_url)!" target="_blank" rel="noopener noreferrer">论文页面 ↗</a><a v-if="safeUrl(result.paper.pdf_url)" :href="safeUrl(result.paper.pdf_url)!" target="_blank" rel="noopener noreferrer">PDF ↗</a></div><button class="button secondary" data-test="save-citation-result" :disabled="!target || adding.has(identity(result.paper)) || added.has(identity(result.paper))" @click="save(result.paper)">{{ adding.has(identity(result.paper)) ? '正在加入…' : added.has(identity(result.paper)) ? '已加入此收藏夹' : '加入收藏夹' }}</button></div>
    <p v-if="errors[identity(result.paper)]" class="notice error" role="alert">{{ errors[identity(result.paper)] }}</p>
   </article>
  </template>
 </section>
</template>

<style scoped>
.citation-report h2,.citation-report h3,.citation-report p{margin:0}.citation-result{overflow-wrap:anywhere}.citation-result h3{font-size:19px}.seed-list{margin:0;padding-left:22px}.seed-list li{padding:5px 0}.citation-paths{list-style:none;padding:0;margin:0}.citation-paths li{border-left:3px solid var(--blue);padding:8px 16px;margin:8px 0;background:var(--paper)}.citation-paths p{margin:6px 0}.citation-paths small{font-family:ui-monospace,monospace;overflow-wrap:anywhere}.evidence{border-left:3px solid var(--green);padding-left:16px}blockquote{margin:10px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}.abstract{white-space:pre-wrap;line-height:1.85;padding-top:12px}summary{color:var(--blue);cursor:pointer}.result-actions{justify-content:space-between}@media(max-width:650px){.result-actions{align-items:flex-start;flex-direction:column}.result-actions>button{width:100%}}
</style>
