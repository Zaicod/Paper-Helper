<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import ReportView from '../components/ReportView.vue'
import StudyReportView from '../components/StudyReportView.vue'
import { createTaskPoller } from '../composables/polling'
import { createSubmission } from '../composables/submission'
import type { Task, TaskStatus, StudyReport, Report } from '../types'

const route = useRoute()
const router = useRouter()
const task = ref<Task | null>(null)
const error = ref('')
const loading = ref(false)
const retrying = ref(false)
const retryError = ref('')
const retrySubmission = createSubmission()
let retryGeneration = 0
const statusLabel: Record<TaskStatus, string> = { queued: '等待执行', running: '正在研究', completed: '研究完成', failed: '执行失败', interrupted: '执行已中断' }
function isStudyReport(report: Report | StudyReport): report is StudyReport { return 'report_type' in report && report.report_type === 'study_report' }
const stageLabel: Record<string, string> = { fetch_pdf: '获取论文正文', study_analyze: '学习分析', study_synthesize: '整理学习总结', export_docx: '生成学习文档', search: '检索论文', index: '构建证据', analyze: '逐篇分析', synthesize: '综合研究', ideate: '生成构思' }
const eventLabel: Record<string, string> = { started: '开始', completed: '完成', failed: '失败' }
const poller = createTaskPoller(id => api.tasks.get(id), value => { task.value = value; loading.value = false; error.value = '' }, cause => { loading.value = false; error.value = cause instanceof Error ? cause.message : '暂时无法同步任务，请重试。' })
function refresh() { loading.value = true; error.value = ''; poller.start(String(route.params.id)) }
watch(() => route.params.id, id => {
  retryGeneration++
  retrySubmission.reset()
  retrying.value = false
  retryError.value = ''
  task.value = null
  if (id) refresh()
  else poller.stop()
}, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { retryGeneration++; poller.stop() })
async function retryTask() {
  if (retrying.value || !task.value || !['failed', 'interrupted'].includes(task.value.status)) return
  const id = String(route.params.id)
  const path = route.path
  const active = retryGeneration
  const isCurrent = () => active === retryGeneration && path === route.path
  retrying.value = true
  retryError.value = ''
  try {
    const result = await api.tasks.retry(id, { idempotency_key: retrySubmission.keyFor({ task_id: id }) })
    if (isCurrent()) await router.push(`/research/${encodeURIComponent(result.task_id)}`)
  } catch (cause) {
    if (isCurrent()) retryError.value = cause instanceof Error ? cause.message : '暂未收到重试结果，请重试。再次点击会沿用同一个任务标识，避免重复执行。'
  } finally { if (isCurrent()) retrying.value = false }
}
function time(value: string) { return new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
</script>

<template>
  <section class="stack">
    <div class="page-heading"><div><p class="eyebrow">RESEARCH RECORD / 研究记录</p><h1>{{ task?.topic ?? '读取研究任务' }}</h1><span v-if="task?.task_type === 'study_report'" class="tag">学习报告</span><p class="task-id muted">{{ route.params.id }}</p></div><RouterLink class="button secondary" :to="{ path: '/research', query: { category: route.query.category, keyword: route.query.keyword, page: route.query.page } }">返回任务</RouterLink></div>
    <div v-if="error" class="notice error" role="alert">{{ error }} <button class="button secondary small" :disabled="loading" @click="refresh">重新同步</button></div>
    <p v-if="loading && !task" class="muted" role="status">正在读取研究记录…</p>
    <template v-if="task">
      <div class="panel progress-panel"><div class="progress-title"><span class="status-dot" :data-status="task.status"></span><h2>{{ statusLabel[task.status] }}</h2><span class="muted">更新于 {{ new Date(task.updated_at).toLocaleString('zh-CN') }}</span></div><p v-if="task.status === 'queued' || task.status === 'running'" class="muted">研究过程会自动更新。你可以离开页面，稍后从任务列表继续查看。</p><p v-if="task.sync_error" class="notice" role="status">{{ task.sync_error }}</p><p v-if="task.error_message" class="notice error" role="alert">{{ task.error_message }}</p>
        <div v-if="task.status === 'failed' || task.status === 'interrupted'" class="stack retry-panel">
          <p class="muted">重试将沿用原任务的主题、论文和学习内容，使用当前默认模型配置创建新任务记录；原任务记录会保留。请先在 <RouterLink to="/settings">个人设置</RouterLink> 中检查配置。</p>
          <p v-if="retryError" data-test="retry-error" class="notice error" role="alert">{{ retryError }}</p>
          <div class="actions"><button class="button primary" data-test="retry-task" :disabled="retrying" @click="retryTask">{{ retrying ? '正在重试…' : '重试任务' }}</button><RouterLink class="button secondary small" to="/research/new">创建新的研究任务</RouterLink></div>
        </div>
        <ol v-if="task.events.length" class="timeline" aria-label="研究阶段记录"><li v-for="(event,index) in task.events" :key="`${index}-${event.timestamp}`" :data-status="event.status"><time :datetime="event.timestamp">{{ time(event.timestamp) }}</time><div><strong>{{ stageLabel[event.stage] ?? event.stage }}</strong><span class="event-label">{{ eventLabel[event.status] ?? event.status }}</span><p>{{ event.message }}</p><small v-if="event.paper_id" class="muted">论文 {{ event.paper_id }}</small></div></li></ol><p v-else class="muted">{{ task.status === 'failed' || task.status === 'interrupted' ? '本次执行未产生阶段记录，可修正配置后重试。' : '等待执行端返回阶段记录。' }}</p>
      </div>
      <template v-if="task.report"><StudyReportView v-if="isStudyReport(task.report)" :report="task.report" :task-id="task.task_id" /><ReportView v-else :report="task.report" /></template>
    </template>
  </section>
</template>

<style scoped>
.task-id { font-family:ui-monospace,monospace; font-size:12px; overflow-wrap:anywhere; }.progress-title { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }.progress-title h2 { font-size:18px; margin:0; }.progress-title > .muted { margin-left:auto; font-size:12px; }.status-dot { width:9px; height:9px; border-radius:50%; background:#245bea; flex-shrink:0; }.status-dot[data-status="completed"] { background:#087f73; }.status-dot[data-status="failed"],.status-dot[data-status="interrupted"] { background:#ad443a; }.timeline { list-style:none; margin:24px 0 0; padding:0; max-height:450px; overflow:auto; }.timeline li { display:grid; grid-template-columns:80px minmax(0,1fr); gap:18px; padding:0 0 22px; }.timeline time { font:12px ui-monospace,monospace; color:#677a92; padding-top:4px; }.timeline li > div { position:relative; padding-left:20px; border-left:2px solid #dae3ef; }.timeline li > div::before { content:''; position:absolute; width:8px; height:8px; top:6px; left:-5px; border-radius:50%; background:#245bea; }.timeline li[data-status="failed"] > div::before { background:#ad443a; }.timeline li[data-status="completed"] > div::before { background:#087f73; }.timeline strong { font-size:14px; }.event-label { font-size:12px; margin-left:10px; color:#677a92; }.timeline p { margin:7px 0; font-size:14px; overflow-wrap:anywhere; }
@media(max-width:560px) { .timeline li { grid-template-columns:64px minmax(0,1fr); gap:8px; }.progress-title > .muted { margin-left:0; width:100%; } }
</style>
