<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import type { Pinia } from 'pinia'
import { getCurrentInstance } from 'vue'
import { api } from '../api'
import PaperDocumentControl from '../components/PaperDocumentControl.vue'
import { DEFAULT_ANALYSIS_TOPIC, DEFAULT_CITATION_TOPIC } from '../composables/analysisTopic'
import type { PaperDocument } from '../types'
import { createSubmission } from '../composables/submission'
import type { Collection, CollectionDetail, TaskInput, ModelSettings, CitationDirection } from '../types'

const pinia = getCurrentInstance()?.appContext.config.globalProperties.$pinia as Pinia | undefined
const owner = computed(() => pinia?.state.value.auth?.user?.id)
const route = useRoute()
const router = useRouter()
const taskType = ref<'research' | 'study_report' | 'citation_trace'>(route.query.task_type === 'citation_trace' ? 'citation_trace' : route.query.task_type === 'study_report' ? 'study_report' : 'research')
const isCitation = computed(() => taskType.value === 'citation_trace')
const citationDirection = ref<CitationDirection>('both')
const maxSeeds = computed(() => isCitation.value ? 5 : 20)
const defaultTopic = computed(() => isCitation.value ? DEFAULT_CITATION_TOPIC : DEFAULT_ANALYSIS_TOPIC)
const isStudy = computed(() => taskType.value === 'study_report')
const learningGoal = ref('')
const reflection = ref('')
const topic = ref('')
const topicEdited = ref(false)
const mode = ref<'demo' | 'live'>('demo')
const limit = ref(3)
const rag = ref<'none' | 'abstract'>('abstract')
const provider = ref<'qwen' | 'openai'>('qwen')
const model = ref('')
const settings = ref<ModelSettings | null>(null)
const providerEdited = ref(false), modelEdited = ref(false)
function updateProvider() {
  providerEdited.value = true
  if (!modelEdited.value) model.value = settings.value?.providers.find(item => item.provider === provider.value)?.model || ''
}
onMounted(async () => {
  const account = owner.value
  try {
    const loaded = await api.modelSettings.get()
    if (!mounted || owner.value !== account) return
    settings.value = loaded
    if (!providerEdited.value && settings.value.default_provider) provider.value = settings.value.default_provider
    if (!modelEdited.value && settings.value.default_provider) model.value = settings.value.providers.find(item => item.provider === provider.value)?.model || ''
  } catch { /* Personal defaults must not block offline demo or existing server settings. */ }
})
const collectionId = ref('')
const collections = ref<Collection[]>([])
const collection = ref<CollectionDetail | null>(null)
const selected = ref<number[]>([])
const collectionLoading = ref(false)
const collectionError = ref('')
const submitting = ref(false)
const error = ref('')
const hasAttempt = ref(false)
const submission = createSubmission()
let collectionGeneration = 0
let mounted = true
onBeforeUnmount(() => { mounted = false; collectionGeneration++ })
watch(owner, () => { collectionGeneration++; documents.value = {}; collection.value = null; selected.value = []; collections.value = []; settings.value = null; submission.reset() }, {flush:'sync'})
const documents = ref<Record<number, PaperDocument | null>>({})
const selectedPapers = computed(() => collection.value?.papers.filter(paper => selected.value.includes(paper.id)) ?? [])
const documentsReady = computed(() => selected.value.length > 0 && selected.value.every(id => documents.value[id]?.status === 'ready'))
watch([selected, isStudy, isCitation], () => {
  if (!topicEdited.value) topic.value = selected.value.length || isStudy.value || isCitation.value ? defaultTopic.value : ''
}, {immediate:true, deep:true})
watch(isCitation, value => { if (value && selected.value.length > 5) selected.value = selected.value.slice(0, 5) })
function restoreDefaultTopic() { topicEdited.value = false; topic.value = defaultTopic.value }


const input = computed<Omit<TaskInput, 'idempotency_key'>>(() => ({
  task_type: taskType.value, ...(isStudy.value ? { learning_goal: learningGoal.value.trim(), reflection: reflection.value.trim() } : {}),
  topic: topic.value.trim(), mode: isStudy.value || isCitation.value ? 'live' : mode.value, limit: Number(limit.value), rag: isCitation.value ? 'none' : rag.value,
  ...(isCitation.value ? { citation_direction: citationDirection.value } : {}),
  ...(!isCitation.value ? { ...(!providerEdited.value && (!settings.value || settings.value.default_provider === null) && (isStudy.value || mode.value === 'live') ? {} : { provider: provider.value }), ...(model.value.trim() ? { model: model.value.trim() } : {}) } : {}),
  ...(collectionId.value ? { collection_id: Number(collectionId.value), paper_ids: [...selected.value].sort((a, b) => a - b) } : {}),
}))
watch(() => route.fullPath, () => { submitting.value = false; submission.reset(); hasAttempt.value = false; error.value = '' }, {flush:'sync'})
watch(() => JSON.stringify(input.value), () => { hasAttempt.value = false }, { flush: 'sync' })
watch(collectionId, async id => {
  const account = owner.value
  const active = ++collectionGeneration
  collection.value = null
  documents.value = {}
  selected.value = []
  collectionError.value = ''
  collectionLoading.value = !!id
  if (!id) return
  try {
    const detail = await api.collections.get(Number(id))
    if (active !== collectionGeneration || owner.value !== account) return
    collection.value = detail
    const ids = String(route.query.paper_ids ?? '').split(',').map(Number).filter(value => Number.isSafeInteger(value) && value > 0)
    selected.value = ids.length && Number(route.query.collection_id) === Number(id) ? detail.papers.filter(paper => ids.includes(paper.id)).slice(0, maxSeeds.value).map(paper => paper.id) : detail.papers.slice(0, maxSeeds.value).map(paper => paper.id)
  } catch (cause) {
    if (active === collectionGeneration) collectionError.value = cause instanceof Error ? cause.message : '收藏夹读取失败，请重新选择。'
  } finally { if (active === collectionGeneration) collectionLoading.value = false }
})
onMounted(async () => {
  try {
    const account = owner.value
    const page = await api.collections.list('', 0, 100)
    if (!mounted || owner.value !== account) return
    collections.value = page.collections
    const requested = Number(route.query.collection_id)
    if (Number.isSafeInteger(requested) && requested > 0) collectionId.value = String(requested)
  } catch (cause) { collectionError.value = cause instanceof Error ? cause.message : '收藏夹列表读取失败。仍可按主题研究。' }
})
async function submit() {
  if (submitting.value) return
  error.value = ''
  if (!input.value.topic) { error.value = '请填写研究主题。'; return }
  if (!Number.isInteger(input.value.limit) || input.value.limit < 1 || input.value.limit > 20) { error.value = '论文数量应为 1 至 20 的整数。'; return }
  if (isCitation.value && (!collectionId.value || !collection.value || selected.value.length < 1 || selected.value.length > 5)) { error.value = '引用追踪需要从收藏夹选择 1 至 5 篇种子论文。'; return }
  if (isStudy.value && !collectionId.value) { error.value = '学习报告需要从收藏夹选择论文。'; return }
  if (collectionId.value && (!collection.value || !selected.value.length || selected.value.length > 20)) { error.value = '请从收藏夹选择 1 至 20 篇论文。'; return }
  if (isStudy.value && !documentsReady.value) { error.value = '请先为所有选中论文准备可用的 PDF 正文。'; return }
  const account = owner.value
  const requestPath = route.fullPath
  const isCurrent = () => mounted && owner.value === account && route.fullPath === requestPath
  const payload: TaskInput = { ...input.value, idempotency_key: submission.keyFor(input.value) }
  submitting.value = true
  hasAttempt.value = true
  try { const task = await api.tasks.create(payload); if (!isCurrent()) return; await router.push(`/research/${task.task_id}`) }
  catch (cause) { if (isCurrent()) error.value = cause instanceof Error ? cause.message : '暂未收到创建结果。保持输入不变后重试可避免重复执行。' }
  finally { if (isCurrent()) submitting.value = false }
}
</script>

<template>
  <section class="stack">
    <div class="page-heading"><div><p class="eyebrow">NEW RESEARCH / 新建研究</p><h1>{{ isCitation ? '追踪论文引用关系' : isStudy ? '生成论文学习报告' : '把问题交给研究流程' }}</h1><p class="muted">确定主题，选择证据范围，再开始分析与综合。</p></div><RouterLink class="button secondary" to="/research">返回任务</RouterLink></div>
    <form class="panel stack" @submit.prevent="submit">
      <fieldset class="stack" :disabled="submitting">
        <label class="field">任务类型<select v-model="taskType"><option value="research">研究分析</option><option value="study_report">学习报告（DOCX）</option><option value="citation_trace">引用追踪</option></select></label>
        <div v-if="isCitation" class="notice">选择 1 至 5 篇种子论文，查找它们的参考文献或引用它们的后续研究。只追踪一层；引用关系不代表支持论文结论。</div><label v-if="isCitation" class="field">追踪方向<select v-model="citationDirection" data-test="citation-direction"><option value="both">双向追踪</option><option value="references">参考文献：种子论文引用了谁</option><option value="citations">后续研究：谁引用了种子论文</option></select></label>
        <div v-if="isStudy" class="notice">先准备开放获取 PDF 或上传已有正文，再依据正文解释模块与实验结果；正文未准备好时不会创建学习任务。</div>
        <label class="field">{{ isCitation ? '希望追踪的研究方向' : selected.length || isStudy ? '读论文的分析要求' : '找论文的研究主题' }}<textarea v-model="topic" @input="topicEdited = true" required maxlength="500" rows="3" placeholder="例如：检索增强生成如何改善论文问答的可靠性？"></textarea><span class="muted">{{ topic.length }} / 500</span></label><button v-if="selected.length || isStudy || isCitation" type="button" class="button secondary small" data-test="restore-default-topic" @click="restoreDefaultTopic">恢复默认分析要求</button>
        <div v-if="!isStudy" class="form-grid"><label v-if="!isCitation" class="field">执行模式<select v-model="mode"><option value="demo">离线演示</option><option value="live">真实模型</option></select></label><label class="field">论文数量上限<input v-model.number="limit" type="number" min="1" max="20" step="1" required></label></div>
        <div v-if="!isStudy && !isCitation && mode === 'demo'" class="notice">演示使用离线示例和演示研究团队，用于学习流程；生成内容不代表真实模型的研究结论。</div>
        <div v-else class="notice">真实模式会调用模型并可能产生费用。请先在 <RouterLink to="/settings">个人设置</RouterLink> 中配置个人密钥与默认大模型，<span v-if="!isCitation">或使用已有的服务端配置。</span><span v-else>引用追踪使用个人默认模型。</span></div>
        <label class="field">论文来源<select v-model="collectionId"><option value="">{{ isStudy || isCitation ? '请选择收藏夹' : '按主题检索' }}</option><option v-for="item in collections" :key="item.id" :value="String(item.id)">{{ item.name }}（{{ item.paper_count }} 篇）</option><option v-if="collectionId && !collections.some(item => String(item.id) === collectionId)" :value="collectionId">指定收藏夹 #{{ collectionId }}</option></select></label>
        <p v-if="collectionError" class="notice error" role="alert">{{ collectionError }}</p>
        <p v-if="collectionLoading" class="muted" role="status">正在读取收藏论文…</p>
        <div v-if="collection" class="paper-choice"><div class="selection-heading"><strong>选择论文</strong><span class="muted">已选 {{ selected.length }} / {{ maxSeeds }}</span></div><p v-if="collection.papers.length > maxSeeds" class="muted">已默认选择前 {{ maxSeeds }} 篇，可调整选择。</p><p v-if="!collection.papers.length" class="muted">该收藏夹还没有论文，请先添加论文或改为按主题检索。</p><label v-for="paper in collection.papers" :key="paper.id" class="paper-option"><input v-model="selected" type="checkbox" :value="paper.id" :disabled="selected.length >= maxSeeds && !selected.includes(paper.id)"><span>{{ paper.title }}<small>{{ paper.source }} · {{ paper.paper_id }}</small></span></label><p class="muted">{{ isCitation ? '选中的论文用于发现引用关系；上方数量上限控制返回结果数量。' : '收藏夹任务仅使用选中的论文；按主题检索时使用上面的数量上限。' }}</p></div>
        <div v-if="isStudy && selectedPapers.length" class="stack"><h3>准备所选论文正文</h3><section v-for="paper in selectedPapers" :key="`${collectionId}-${paper.id}`"><strong>{{ paper.title }}</strong><PaperDocumentControl :collection-id="Number(collectionId)" :paper="paper" @status="documents[paper.id] = $event" /></section><p v-if="!documentsReady" role="status" class="notice">请先准备所有选中论文的正文，再生成学习报告。</p></div>
        <template v-if="isStudy"><label class="field">学习目标（可选）<textarea v-model="learningGoal" rows="3" maxlength="2000" placeholder="例如：理解融合模块的输入、输出与作用" /></label><label class="field">我的阅读体会（可选）<textarea v-model="reflection" rows="3" maxlength="4000" placeholder="Agent 将结合你的记录整理学习体会；未提供时明确标注为学习建议。" /></label></template>
        <p v-if="!isStudy && !isCitation && mode === 'demo'" class="muted">真实任务的凭证与默认模型可在 <RouterLink to="/settings">个人设置</RouterLink> 中管理。</p>
        <details v-if="!isCitation" class="advanced"><summary>研究设置</summary><p v-if="(isStudy || mode === 'live') && !settings && !providerEdited" class="muted">个人设置正在读取或暂时不可用，提交时会使用账号或服务端的默认配置；也可手动选择提供方。</p><p v-if="settings?.default_provider === null && !providerEdited" class="muted">当前使用服务端默认提供方与模型；选择下方提供方可改用该提供方的个人设置。</p><div class="form-grid"><label v-if="!isStudy" class="field">证据检索<select v-model="rag"><option value="abstract">摘要 RAG</option><option value="none">不使用 RAG</option></select></label><label class="field">模型提供方<select v-model="provider" data-test="task-provider" @change="updateProvider"><option value="qwen">Qwen</option><option value="openai">OpenAI</option></select></label></div><label class="field">模型名称（可选）<input v-model="model" data-test="task-model" maxlength="128" placeholder="留空使用已保存或服务端默认模型" @input="modelEdited = true"></label></details>
      </fieldset>
      <p v-if="error" class="notice error" role="alert">{{ error }}</p>
      <div class="actions"><button class="button primary" type="submit" :disabled="submitting || collectionLoading || (isStudy && !documentsReady)">{{ submitting ? '正在创建…' : hasAttempt && error ? '重试创建任务' : isCitation ? '开始引用追踪' : isStudy ? '生成学习报告' : '开始研究' }}</button><span v-if="hasAttempt && error" class="muted retry-note">输入不变时会沿用同一个任务标识，避免重复执行。</span></div>
    </form>
  </section>
</template>

<style scoped>
fieldset { border: 0; margin: 0; padding: 0; min-width: 0; }.paper-choice { border: 1px solid #dae3ef; border-radius: 10px; padding: 18px; }.selection-heading { display: flex; justify-content: space-between; gap: 16px; }.paper-option { display: flex; gap: 12px; padding: 14px 0; border-bottom: 1px solid #e8edf5; align-items: flex-start; }.paper-option input { width: auto; margin-top: 5px; }.paper-option small { display:block; color:#677a92; font-size:12px; margin-top:5px; }.advanced summary { cursor:pointer; color:#245bea; margin-bottom:18px; }.advanced > .field { margin-top:16px; }.retry-note { font-size:13px; max-width:420px; }textarea { resize:vertical; }
</style>
