<script setup lang="ts">
import type { StudyReport } from '../types'
defineProps<{ report: StudyReport; taskId: string }>()
function safeUrl(value: string) {
  if (/^\/api\/library\/documents\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/file$/i.test(value)) return value
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null }
  catch { return null }
}
</script>

<template>
  <article class="study-report stack" aria-label="论文学习报告">
    <header class="report-heading"><div><p class="eyebrow">STUDY REPORT / 论文学习报告</p><h2>{{ report.topic }}</h2><p class="muted">根据论文正文生成 · {{ new Date(report.generated_at).toLocaleString('zh-CN') }}</p></div><a class="button primary" :href="`/api/research/tasks/${encodeURIComponent(taskId)}/document`" download>下载 DOCX 学习报告</a></header>
    <section v-for="(analysis,index) in report.analyses" :key="analysis.paper_id" class="panel stack">
      <div><p class="eyebrow">PAPER {{ String(index + 1).padStart(2, '0') }} / {{ analysis.paper_id }}</p><h2>{{ analysis.title }}</h2></div>
      <section><h3>论文概述</h3><p>{{ analysis.overview }}</p></section>
      <section><h3>1. 研究背景与问题</h3><p>{{ analysis.background }}</p></section>
      <section><h3>2. 模型方法（模块解释）</h3><div v-for="(method,methodIndex) in analysis.methods" :key="methodIndex" class="method"><h4>{{ method.name }}</h4><p>{{ method.purpose }}</p><dl><dt>输入</dt><dd>{{ method.inputs }}</dd><dt>输出</dt><dd>{{ method.outputs }}</dd></dl></div></section>
      <section><h3>3. 创新点 &amp; 实验结果</h3><h4>创新点</h4><ul><li v-for="(item,itemIndex) in analysis.innovations" :key="itemIndex">{{ item }}</li></ul><h4>实验结果</h4><ul><li v-for="(item,itemIndex) in analysis.results" :key="itemIndex">{{ item }}</li></ul></section>
      <section><h3>4. 学习体会</h3><p class="muted">Agent 根据论文与提供的阅读记录整理，请结合自己的理解核对。</p><ul><li v-for="(item,itemIndex) in analysis.reflection" :key="itemIndex">{{ item }}</li></ul></section>
      <details class="evidence"><summary>正文证据与页码</summary><ul><li v-for="(citation,citationIndex) in analysis.citations" :key="citationIndex"><a v-if="safeUrl(citation.source_url)" :href="safeUrl(citation.source_url)!" target="_blank" rel="noopener noreferrer">{{ citation.chunk_id }}</a><span v-else>{{ citation.chunk_id }}</span> · {{ citation.page_number === null ? '未提供页码' : `第 ${citation.page_number} 页` }}</li></ul></details>
    </section>
    <section v-if="report.synthesis.length" class="panel"><h2>多篇对比与总结</h2><ul><li v-for="(item,index) in report.synthesis" :key="index">{{ item }}</li></ul></section>
    <section class="panel"><h2>后续学习计划</h2><ul><li v-for="(item,index) in report.learning_plan" :key="index">{{ item }}</li></ul></section>
  </article>
</template>

<style scoped>
.study-report { overflow-wrap:anywhere; }.report-heading { border-top:3px solid #182b45; padding-top:24px; display:flex; justify-content:space-between; gap:20px; align-items:flex-start; }.report-heading h2 { margin:8px 0; font-size:25px; }.study-report h3 { font-size:17px; color:#245bea; margin:0 0 12px; }.study-report h4 { font-size:15px; margin:0 0 8px; }.study-report p,.study-report li,.study-report dd { line-height:1.85; white-space:pre-wrap; }.study-report ul { padding-left:22px; }.study-report li + li { margin-top:8px; }.method { border-left:3px solid #dae3ef; padding:8px 18px; margin-top:16px; }.method dl { display:grid; grid-template-columns:40px minmax(0,1fr); gap:8px; font-size:14px; }.method dt { color:#677a92; }.method dd { margin:0; }.evidence { padding-top:16px; border-top:1px solid #dae3ef; font-size:13px; }.evidence summary { cursor:pointer; }.evidence a { color:#245bea; }
@media(max-width:700px) { .report-heading { flex-direction:column; }.report-heading .button { width:100%; justify-content:center; } }
</style>
