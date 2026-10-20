<script setup lang="ts">
import { computed } from 'vue'
import type { Analysis, Report, ResearchIdea } from '../types'

const props = defineProps<{ report: Report }>()
function safeUrl(value: string | null | undefined) {
  if (!value) return null
  try { const parsed = new URL(value); return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null }
  catch { return null }
}
const synthesisGroups = computed(() => [
  { label: '方法分类', items: props.report.synthesis.method_taxonomy },
  { label: '共同发现', items: props.report.synthesis.common_findings },
  { label: '分歧与差异', items: props.report.synthesis.disagreements },
  { label: '研究空白', items: props.report.synthesis.research_gaps },
  { label: '证据对应', items: props.report.synthesis.evidence_map },
])
function analysisGroups(analysis: Analysis) {
  return [
    { label: '创新点', items: analysis.innovation_points }, { label: '方法', items: analysis.methods },
    { label: '结果', items: analysis.results }, { label: '局限', items: analysis.limitations },
    { label: '证据说明', items: analysis.evidence_notes }, { label: '数据集', items: analysis.datasets },
    { label: '引用与证据标识', items: analysis.citations },
  ]
}
function ideaGroups(idea: ResearchIdea) {
  return [
    { label: '方法步骤', items: idea.proposed_method }, { label: '评估计划', items: idea.evaluation_plan },
    { label: '风险', items: idea.risks }, { label: '相关论文', items: idea.related_paper_ids },
  ]
}
</script>

<template>
  <article class="research-report stack" aria-label="研究报告">
    <header class="report-heading"><div><p class="eyebrow">RESEARCH REPORT / 研究报告</p><h2>{{ report.topic }}</h2></div><p class="muted">{{ new Date(report.generated_at).toLocaleString('zh-CN') }}</p></header>
    <section class="panel stack"><h2>综合理解</h2><p class="overview">{{ report.synthesis.overview }}</p><div class="report-grid"><section v-for="group in synthesisGroups" :key="group.label" class="report-block"><h3>{{ group.label }}</h3><ul v-if="group.items.length"><li v-for="(item,index) in group.items" :key="index">{{ item }}</li></ul><p v-else class="muted">本次报告未提供此项内容。</p></section></div></section>
    <section class="panel stack"><div class="section-title"><h2>逐篇分析</h2><span class="tag">{{ report.analyses.length }} 篇已完成</span></div><p v-if="!report.analyses.length" class="muted">本次没有完成逐篇分析。</p><details v-for="(analysis,index) in report.analyses" :key="analysis.paper_id" class="paper-analysis" :open="index === 0"><summary><span class="analysis-number">{{ String(index + 1).padStart(2,'0') }}</span><span>{{ analysis.title }}</span></summary><div class="analysis-body stack"><p class="paper-id muted">论文标识 {{ analysis.paper_id }}</p><section><h3>研究问题</h3><p>{{ analysis.research_problem }}</p></section><div class="report-grid"><section v-for="group in analysisGroups(analysis)" :key="group.label" class="report-block"><h3>{{ group.label }}</h3><ul v-if="group.items.length"><li v-for="(item,itemIndex) in group.items" :key="itemIndex">{{ item }}</li></ul><p v-else class="muted">未提供。</p></section></div></div></details></section>
    <section v-if="report.analysis_failures.length" class="panel stack"><h2>未完成的论文分析</h2><p class="muted">以下论文没有完成分析，阅读综合结论时请考虑这一范围限制。</p><div v-for="failure in report.analysis_failures" :key="`${failure.paper_id}-${failure.stage}`" class="notice error"><strong>{{ failure.paper_id }}</strong><p>{{ failure.message || '该论文在此阶段执行失败。' }}</p><small>阶段 {{ failure.stage }} · {{ failure.error_type }} · 重试 {{ failure.retry_count }} 次</small></div></section>
    <section class="panel stack"><div class="section-title"><h2>可检验的研究构思</h2><span class="tag">{{ report.idea_portfolio.ideas.length }} 项</span></div><p class="notice">{{ report.idea_portfolio.caution }}</p><section v-for="(idea,index) in report.idea_portfolio.ideas" :key="index" class="idea"><p class="eyebrow">IDEA {{ String(index + 1).padStart(2,'0') }}</p><h3>{{ idea.title }}</h3><dl><dt>针对的空白</dt><dd>{{ idea.target_gap }}</dd><dt>研究假设</dt><dd>{{ idea.hypothesis }}</dd><dt>预期贡献</dt><dd>{{ idea.expected_contribution }}</dd></dl><div class="report-grid"><section v-for="group in ideaGroups(idea)" :key="group.label" class="report-block"><h4>{{ group.label }}</h4><ul v-if="group.items.length"><li v-for="(item,itemIndex) in group.items" :key="itemIndex">{{ item }}</li></ul><p v-else class="muted">未提供。</p></section></div></section></section>
    <section class="panel stack"><div class="section-title"><h2>证据审计</h2><span class="tag">{{ report.context_audits.length }} 条记录</span></div><p class="muted">查看每次分析使用的证据片段、上下文预算和来源模式。</p><p v-if="!report.context_audits.length" class="muted">本次未生成证据审计，可能未启用 RAG。</p><details v-for="(audit,index) in report.context_audits" :key="`${audit.paper_id}-${index}`" class="audit"><summary>{{ audit.paper_id }} <span class="muted">{{ audit.source_mode }} · {{ audit.estimated_tokens }} / {{ audit.token_budget }} tokens</span></summary><dl><dt>检索问题</dt><dd>{{ audit.query }}</dd><dt>已选片段</dt><dd class="chunk-ids">{{ audit.selected_chunk_ids.join('、') || '无' }}</dd><dt>舍弃片段数</dt><dd>{{ audit.dropped_count }}</dd></dl><ul v-if="audit.decisions.length"><li v-for="(decision,decisionIndex) in audit.decisions" :key="decisionIndex">{{ decision.action }} · 置信度 {{ (decision.confidence * 100).toFixed(1) }}% · {{ decision.source }}</li></ul></details></section>
    <section class="panel stack"><h2>本次论文资料</h2><section v-for="paper in report.papers" :key="`${paper.source}-${paper.paper_id}`" class="source-paper"><h3>{{ paper.title }}</h3><p class="muted">{{ paper.authors.join('、') || '未提供作者' }}<span v-if="paper.published"> · {{ paper.published }}</span></p><p class="paper-id muted">{{ paper.source }} · {{ paper.paper_id }}<span v-if="paper.categories.length"> · {{ paper.categories.join(' / ') }}</span></p><p>{{ paper.abstract || '未提供摘要。' }}</p><div class="actions"><a v-if="safeUrl(paper.page_url)" :href="safeUrl(paper.page_url)!" target="_blank" rel="noopener noreferrer" class="source-link">论文页面 ↗</a><a v-if="safeUrl(paper.pdf_url)" :href="safeUrl(paper.pdf_url)!" target="_blank" rel="noopener noreferrer" class="source-link">PDF 链接 ↗</a></div></section></section>
  </article>
</template>

<style scoped>
.research-report { overflow-wrap:anywhere; }.report-heading { border-top:3px solid #182b45; padding-top:24px; display:flex; justify-content:space-between; gap:20px; align-items:flex-start; }.report-heading h2 { font-size:25px; margin:8px 0 0; }.report-heading > p { font-size:12px; white-space:nowrap; }.research-report > .panel > h2,.section-title h2 { font-size:20px; margin:0; }.research-report h3 { font-size:16px; margin:0 0 12px; }.research-report h4 { font-size:14px; margin:0 0 8px; }.research-report p,.research-report li,.research-report dd { line-height:1.85; }.overview { font-size:16px; white-space:pre-wrap; }.report-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:24px 28px; }.report-block h3 { font-size:14px; color:#245bea; margin:0 0 8px; }.report-block p,.report-block ul { font-size:14px; margin:0; }.research-report ul { padding-left:19px; }.research-report li + li { margin-top:7px; }.section-title { display:flex; justify-content:space-between; align-items:center; gap:16px; }.paper-analysis { border-top:1px solid #dae3ef; padding-top:18px; }.paper-analysis summary { display:flex; align-items:baseline; gap:16px; cursor:pointer; font-weight:600; line-height:1.7; }.paper-analysis summary::before { content:'＋'; color:#245bea; }.paper-analysis[open] summary::before { content:'−'; }.analysis-number { color:#677a92; font:13px ui-monospace,monospace; }.analysis-body { margin-top:18px; }.paper-id { font:12px ui-monospace,monospace; }.idea { border-top:1px solid #dae3ef; padding-top:22px; }.idea > h3 { font-size:19px; }.research-report dl { margin:12px 0 22px; }.research-report dt { font-size:12px; font-weight:600; color:#677a92; margin-top:14px; }.research-report dd { margin:5px 0 0; font-size:14px; }.audit { border-left:3px solid #245bea; padding:12px 16px; background:#f4f7fb; }.audit summary { cursor:pointer; font-size:14px; font-weight:600; }.audit summary .muted { font-size:12px; font-weight:400; margin-left:10px; }.chunk-ids { font-family:ui-monospace,monospace; }.source-paper + .source-paper { border-top:1px solid #dae3ef; padding-top:22px; }.source-paper p { font-size:14px; }.source-link { color:#245bea; font-size:13px; }.research-report .notice p { margin:7px 0; }
@media(max-width:700px) { .report-grid { grid-template-columns:1fr; gap:20px; }.report-heading { flex-direction:column; gap:4px; }.report-heading > p { margin-top:0; }.audit summary .muted { display:block; margin:8px 0 0; } }
</style>
