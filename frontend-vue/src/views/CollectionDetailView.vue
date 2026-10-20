<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import type { CollectionDetail, Paper, PaperInput } from '../types'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))
const collection = ref<CollectionDetail | null>(null)
const loading = ref(true)
const saving = ref('')
const error = ref('')
const success = ref('')
const selectedStudyPapers = ref<number[]>([])
function studyLink(ids: number[]) { return { path: '/research/new', query: { task_type: 'study_report', collection_id: id.value, paper_ids: ids.join(',') } } }
const overallNote = ref('')
const notes = reactive<Record<number, string>>({})
const metadata = reactive({ name: '', description: '' })
const blankPaper = () => ({ source: 'manual', paper_id: '', title: '', abstract: '', authors: '', categories: '', published: '', page_url: '', pdf_url: '' })
const draft = reactive(blankPaper())
const editPaperId = ref<number | null>(null)
const editDraft = reactive(blankPaper())
let requestNumber = 0

function message(cause: unknown) {
  return cause instanceof Error ? cause.message : '操作未完成，请稍后重试。'
}

function safeUrl(value: string) {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password && url.hostname ? url.href : null
  } catch {
    return null
  }
}

async function load(preserveDrafts = false) {
  const request = ++requestNumber
  const currentId = id.value
  loading.value = true
  if (!Number.isSafeInteger(currentId) || currentId <= 0) {
    error.value = '收藏夹地址无效。'
    loading.value = false
    return
  }
  try {
    const result = await api.collections.get(currentId)
    if (request !== requestNumber) return
    collection.value = result
    selectedStudyPapers.value = selectedStudyPapers.value.filter(id => result.papers.some(paper => paper.id === id))
    if (!preserveDrafts) {
      overallNote.value = result.overall_note
      metadata.name = result.name
      metadata.description = result.description
      for (const key of Object.keys(notes)) delete notes[Number(key)]
    }
    for (const paper of result.papers) {
      if (!preserveDrafts || !(paper.id in notes)) notes[paper.id] = paper.note
    }
  } catch (cause) {
    if (request === requestNumber) error.value = message(cause)
  } finally {
    if (request === requestNumber) loading.value = false
  }
}

async function perform(key: string, action: (currentId: number) => Promise<unknown>, confirmation: string) {
  if (saving.value) return
  const currentId = id.value
  saving.value = key
  error.value = ''
  success.value = ''
  try {
    await action(currentId)
    if (currentId !== id.value) return
    success.value = confirmation
  } catch (cause) {
    if (currentId === id.value) error.value = message(cause)
  } finally {
    if (currentId === id.value) saving.value = ''
  }
}

function saveNote() {
  return perform('overall-note', currentId => api.collections.note(currentId, overallNote.value), '收藏夹笔记已保存。')
}

function savePaperNote(paper: Paper) {
  return perform('paper-note-' + paper.id, currentId => api.collections.paperNote(currentId, {
    source: paper.source, paper_id: paper.paper_id, content: notes[paper.id] ?? '',
  }), '论文笔记已保存。')
}

async function saveMetadata() {
  if (!metadata.name.trim()) {
    error.value = '请填写收藏夹名称。'
    return
  }
  await perform('metadata', async currentId => {
    const result = await api.collections.update(currentId, { name: metadata.name.trim(), description: metadata.description })
    if (currentId === id.value && collection.value) {
      collection.value.name = result.name
      collection.value.description = result.description
    }
  }, '收藏夹信息已保存。')
}

async function removeCollection() {
  if (!collection.value || saving.value || !window.confirm(`确定删除「${collection.value.name}」及其中的个人笔记？已提交的研究任务历史会保留。`)) return
  await perform('delete', async currentId => {
    await api.collections.remove(currentId)
    if (currentId === id.value) await router.push('/collections')
  }, '收藏夹已删除。')
}

async function removePaper(paper: Paper) {
  if (saving.value || !window.confirm(`确定从当前收藏夹移除「${paper.title}」及其个人笔记？`)) return
  await perform('remove-' + paper.id, async currentId => {
    await api.collections.removePaper(currentId, paper.id)
    if (currentId === id.value) {
      delete notes[paper.id]
      await load(true)
    }
  }, '论文已从收藏夹移除。')
}

function splitMetadata(value: string) {
  return value.split(/[,，\r\n]+/).map(item => item.trim()).filter(Boolean)
}

async function editPaper(paper: Paper) {
  await perform('read-paper-' + paper.id, async currentId => {
    const stored = await api.collections.paper(currentId, paper.id)
    if (currentId !== id.value) return
    Object.assign(editDraft, { source: stored.source, paper_id: stored.paper_id, title: stored.title,
      abstract: stored.abstract, authors: stored.authors.join('\n'), categories: stored.categories.join('\n'),
      published: stored.published || '', page_url: stored.page_url, pdf_url: stored.pdf_url || '' })
    editPaperId.value = stored.id
  }, '')
}

async function saveEditedPaper() {
  if (saving.value || editPaperId.value === null) return
  if (!editDraft.title.trim()) { error.value = '请填写论文标题。'; return }
  if (!safeUrl(editDraft.page_url.trim()) || (editDraft.pdf_url.trim() && !safeUrl(editDraft.pdf_url.trim()))) {
    error.value = '论文链接与 PDF 链接必须是有效的 HTTP 或 HTTPS 地址，且不能包含账号密码。'; return
  }
  // Source names can contain commas; editing another field must preserve each author.
  const authors = editDraft.authors.split(/[\r\n]+/).map(item => item.trim()).filter(Boolean)
  const categories = editDraft.categories.split(/[\r\n]+/).map(item => item.trim()).filter(Boolean)
  if (authors.length > 50 || authors.some(item => item.length > 128) || categories.length > 50 || categories.some(item => item.length > 64)) {
    error.value = '作者与分类各限 50 项，作者每项最多 128 字，分类每项最多 64 字。'; return
  }
  const paperId = editPaperId.value
  const input: PaperInput = { source: editDraft.source, paper_id: editDraft.paper_id, title: editDraft.title.trim(),
    abstract: editDraft.abstract, authors, categories, published: editDraft.published.trim() || null,
    page_url: editDraft.page_url.trim(), pdf_url: editDraft.pdf_url.trim() || null }
  await perform('edit-paper-' + paperId, async currentId => {
    const updated = await api.collections.updatePaper(currentId, paperId, input)
    if (currentId !== id.value || !collection.value) return
    collection.value.papers = collection.value.papers.map(item => item.id === paperId ? updated : item)
    editPaperId.value = null
  }, '论文资料已保存，仅影响当前收藏夹。个人笔记和已提交的研究任务保持原样。')
}

async function addPaper() {
  if (saving.value) return
  error.value = ''
  success.value = ''
  if (!draft.source.trim() || !draft.paper_id.trim() || !draft.title.trim()) {
    error.value = '请填写来源、来源论文 ID 和论文标题。'
    return
  }
  if (!safeUrl(draft.page_url.trim()) || (draft.pdf_url.trim() && !safeUrl(draft.pdf_url.trim()))) {
    error.value = '论文链接与 PDF 链接必须是有效的 HTTP 或 HTTPS 地址，且不能包含账号密码。'
    return
  }
  const authors = splitMetadata(draft.authors)
  const categories = splitMetadata(draft.categories)
  if (authors.length > 50 || authors.some(author => author.length > 128) || categories.length > 50 || categories.some(category => category.length > 64)) {
    error.value = '作者与分类各限 50 项，作者每项最多 128 字，分类每项最多 64 字。'
    return
  }
  const input: PaperInput = {
    source: draft.source.trim(), paper_id: draft.paper_id.trim(), title: draft.title.trim(),
    abstract: draft.abstract, authors, categories, published: draft.published.trim() || null,
    page_url: draft.page_url.trim(), pdf_url: draft.pdf_url.trim() || null,
  }
  await perform('import', async currentId => {
    await api.collections.addPaper(currentId, input)
    if (currentId === id.value) {
      Object.assign(draft, blankPaper())
      await load(true)
    }
  }, '论文已加入收藏夹。已有相同来源与 ID 时，会保留已存的论文信息和个人笔记。')
}

watch(() => route.params.id, () => {
  collection.value = null
  selectedStudyPapers.value = []
  error.value = ''
  success.value = ''
  saving.value = ''
  editPaperId.value = null
  Object.assign(draft, blankPaper())
  void load()
}, { immediate: true })
</script>

<template>
  <div class="stack collection-detail">
    <RouterLink to="/collections" class="back-link">← 全部收藏夹</RouterLink>
    <p v-if="error" role="alert" class="notice error">{{ error }}</p>
    <p v-if="success" role="status" class="notice success">{{ success }}</p>
    <p v-if="loading && !collection" role="status" class="muted">正在读取收藏夹…</p>
    <div v-if="!loading && !collection" class="panel empty-state">
      <h1>暂时无法打开收藏夹</h1>
      <p class="muted">收藏夹可能已删除，或当前账号无权访问。</p>
      <button class="button secondary" @click="load()">重新读取</button>
    </div>

    <template v-if="collection">
      <header class="page-heading">
        <div class="collection-heading-copy">
          <p class="eyebrow">COLLECTION / {{ collection.paper_count }} PAPERS</p>
          <h1>{{ collection.name }}</h1>
          <p class="muted collection-description">{{ collection.description || '为这个收藏夹添加描述，记录你的研究范围。' }}</p>
        </div>
        <div class="actions">
          <RouterLink class="button primary" :to="{ path: '/research/new', query: { collection_id: collection.id } }">基于收藏夹发起研究</RouterLink>
          <a href="#paper-import" class="button secondary">录入论文</a>
        </div>
      </header>

      <div class="detail-layout">
        <section class="stack papers-column" aria-labelledby="papers-heading">
          <div class="section-heading"><h2 id="papers-heading">论文与阅读笔记</h2><span class="muted">{{ collection.paper_count }} 篇</span></div>
          <div v-if="collection.papers.length" class="panel actions"><span class="muted">勾选 1 至 20 篇生成学习报告 · 已选 {{ selectedStudyPapers.length }} 篇</span><button type="button" class="button secondary small" data-test="select-study-papers" @click="selectedStudyPapers = collection.papers.slice(0, 20).map(paper => paper.id)">{{ collection.papers.length > 20 ? '选择前 20 篇' : '全选' }}</button><button type="button" class="button secondary small" data-test="clear-study-papers" :disabled="!selectedStudyPapers.length" @click="selectedStudyPapers = []">清空选择</button><RouterLink v-if="selectedStudyPapers.length" class="button primary small" :to="studyLink(selectedStudyPapers)">生成所选论文学习报告</RouterLink><span v-else class="muted">请先勾选论文</span></div>
          <div v-if="collection.papers.length === 0" class="panel empty-state">
            <h3>还没有论文</h3>
            <p>在下方录入论文信息和摘要，再整理证据或发起研究。</p>
            <a href="#paper-import" class="button secondary">录入第一篇论文</a>
          </div>
          <article v-for="paper in collection.papers" :key="paper.id" class="panel paper-card">
            <div class="paper-meta"><span class="tag">{{ paper.source === 'manual' ? '人工录入' : paper.source }}</span><span v-if="paper.metadata_edited" class="tag">本收藏夹个人编辑</span><span class="muted paper-external-id">{{ paper.paper_id }}</span></div>
            <label class="study-selection"><input v-model="selectedStudyPapers" type="checkbox" :value="paper.id" :disabled="selectedStudyPapers.length >= 20 && !selectedStudyPapers.includes(paper.id)" :aria-label="`选择学习报告论文：${paper.title}`">加入学习报告</label>
            <h3>{{ paper.title }}</h3>
            <RouterLink class="button secondary small" :to="studyLink([paper.id])">生成单篇学习报告</RouterLink>
            <p v-if="paper.authors.length" class="muted">{{ paper.authors.join(' · ') }}</p>
            <div class="actions paper-links">
              <a v-if="safeUrl(paper.page_url)" :href="safeUrl(paper.page_url)!" target="_blank" rel="noopener noreferrer">论文页面 ↗</a>
              <a v-if="paper.pdf_url && safeUrl(paper.pdf_url)" :href="safeUrl(paper.pdf_url)!" target="_blank" rel="noopener noreferrer">PDF ↗</a>
              <span v-if="paper.published" class="muted">{{ paper.published }}</span>
            </div>
            <p v-if="paper.abstract" class="paper-abstract">{{ paper.abstract }}</p>
            <p v-else class="muted">暂无摘要；摘要是研究分析的重要证据来源。</p>
            <div v-if="paper.categories.length" class="actions category-tags"><span v-for="(category, index) in paper.categories" :key="index" class="tag">{{ category }}</span></div>
            <button class="button secondary small" type="button" :data-test="`edit-paper-${paper.id}`" :disabled="!!saving" @click="editPaper(paper)">编辑论文资料</button>
            <form v-if="editPaperId === paper.id" class="stack personal-paper-editor" data-test="paper-edit-form" @submit.prevent="saveEditedPaper">
              <h4>当前收藏夹的个人论文资料</h4><p class="muted">修改只影响本收藏夹的论文资料与后续研究输入。来源标识固定，个人笔记另行保存。</p>
              <fieldset class="import-fields" :disabled="!!saving">
                <legend class="visually-hidden">编辑论文元数据</legend>
                <div class="form-grid"><label class="field" for="edit-paper-source">来源<input id="edit-paper-source" v-model="editDraft.source" class="input" readonly></label><label class="field" for="edit-paper-id">来源论文 ID<input id="edit-paper-id" v-model="editDraft.paper_id" class="input" readonly></label></div>
                <label class="field" for="edit-paper-title">标题<input id="edit-paper-title" v-model="editDraft.title" class="input" required maxlength="1024"></label>
                <label class="field" for="edit-paper-abstract">摘要<textarea id="edit-paper-abstract" v-model="editDraft.abstract" class="textarea" rows="5" maxlength="10000" /></label>
                <div class="form-grid"><label class="field" for="edit-paper-authors">作者（每行一位，保留姓名中的逗号）<textarea id="edit-paper-authors" v-model="editDraft.authors" class="textarea" rows="3" /></label><label class="field" for="edit-paper-categories">分类（每行一项）<textarea id="edit-paper-categories" v-model="editDraft.categories" class="textarea" rows="3" /></label></div>
                <label class="field" for="edit-paper-published">发表时间<input id="edit-paper-published" v-model="editDraft.published" class="input" maxlength="64"></label>
                <label class="field" for="edit-paper-url">论文页面链接<input id="edit-paper-url" v-model="editDraft.page_url" class="input" type="url" required maxlength="2048"></label>
                <label class="field" for="edit-paper-pdf">PDF 链接（可选）<input id="edit-paper-pdf" v-model="editDraft.pdf_url" class="input" type="url" maxlength="2048"></label>
              </fieldset>
              <div class="actions"><button class="button primary small" :disabled="!!saving">{{ saving === 'edit-paper-' + paper.id ? '正在保存…' : '保存个人资料' }}</button><button class="button secondary small" type="button" :disabled="!!saving" @click="editPaperId = null">取消编辑</button></div>
            </form>
            <form class="paper-note-form" @submit.prevent="savePaperNote(paper)">
              <label class="label" :for="`paper-note-${paper.id}`">个人阅读笔记</label>
              <textarea :id="`paper-note-${paper.id}`" v-model="notes[paper.id]" class="textarea" rows="3" maxlength="50000" placeholder="记录证据、疑问或实验想法" :disabled="!!saving" />
              <div class="actions paper-note-actions">
                <button class="button secondary small" :disabled="!!saving">{{ saving === 'paper-note-' + paper.id ? '正在保存…' : '保存论文笔记' }}</button>
                <button type="button" class="button danger small" :disabled="!!saving" :aria-label="`移除论文：${paper.title}`" @click="removePaper(paper)">{{ saving === 'remove-' + paper.id ? '正在移除…' : '移除论文' }}</button>
              </div>
            </form>
          </article>
        </section>

        <aside class="stack notes-column">
          <section class="panel" aria-labelledby="collection-note-heading">
            <p class="eyebrow">RESEARCH NOTEBOOK</p>
            <h2 id="collection-note-heading">收藏夹笔记</h2>
            <p class="muted note-help">写下研究问题、论文间的联系，以及下一步要验证的想法。</p>
            <form class="stack" data-test="collection-note-form" @submit.prevent="saveNote">
              <label class="label" for="overall-note">研究笔记</label>
              <textarea id="overall-note" v-model="overallNote" class="textarea" rows="10" maxlength="50000" :disabled="!!saving" />
              <button class="button primary" :disabled="!!saving">{{ saving === 'overall-note' ? '正在保存…' : '保存收藏夹笔记' }}</button>
            </form>
          </section>
          <details class="panel metadata-editor">
            <summary>编辑收藏夹信息</summary>
            <form class="stack" @submit.prevent="saveMetadata">
              <div class="field"><label class="label" for="detail-name">收藏夹名称</label><input id="detail-name" v-model="metadata.name" class="input" required maxlength="255" :disabled="!!saving" /></div>
              <div class="field"><label class="label" for="detail-description">描述</label><textarea id="detail-description" v-model="metadata.description" class="textarea" maxlength="2000" rows="3" :disabled="!!saving" /></div>
              <button class="button secondary" :disabled="!!saving">保存收藏夹信息</button>
              <button class="button danger" type="button" :disabled="!!saving" @click="removeCollection">删除收藏夹</button>
            </form>
          </details>
        </aside>
      </div>

      <section id="paper-import" class="panel import-panel" aria-labelledby="paper-import-heading">
        <div class="section-heading"><div><p class="eyebrow">ADD YOUR SOURCE</p><h2 id="paper-import-heading">录入论文</h2></div><span class="tag">人工填写元数据</span></div>
        <p class="muted">填写原始来源与摘要。人工录入的信息尚未核验，来源与论文 ID 相同时会复用已有记录。</p>
        <form class="stack" data-test="paper-import-form" @submit.prevent="addPaper">
          <fieldset :disabled="!!saving" class="import-fields">
            <legend class="visually-hidden">论文信息</legend>
            <div class="form-grid">
              <div class="field"><label class="label" for="paper-source">来源 *</label><input id="paper-source" v-model="draft.source" class="input" required maxlength="64" placeholder="manual / arxiv / openalex" /></div>
              <div class="field"><label class="label" for="paper-id">来源论文 ID *</label><input id="paper-id" v-model="draft.paper_id" class="input" required maxlength="255" placeholder="例如：2401.12345" /></div>
            </div>
            <div class="field"><label class="label" for="paper-title">论文标题 *</label><input id="paper-title" v-model="draft.title" class="input" required maxlength="1024" /></div>
            <div class="field"><label class="label" for="paper-abstract">摘要</label><textarea id="paper-abstract" v-model="draft.abstract" class="textarea" rows="5" maxlength="10000" placeholder="粘贴论文摘要，供 Agent 检索与分析" /></div>
            <div class="form-grid">
              <div class="field"><label class="label" for="paper-authors">作者</label><textarea id="paper-authors" v-model="draft.authors" class="textarea" rows="2" placeholder="用换行或逗号分隔" /></div>
              <div class="field"><label class="label" for="paper-categories">分类</label><textarea id="paper-categories" v-model="draft.categories" class="textarea" rows="2" placeholder="例如：cs.AI, cs.IR" /></div>
            </div>
            <div class="form-grid">
              <div class="field"><label class="label" for="paper-url">论文页面链接 *</label><input id="paper-url" v-model="draft.page_url" class="input" type="url" required maxlength="2048" placeholder="https://" /></div>
              <div class="field"><label class="label" for="paper-pdf-url">PDF 链接（可选）</label><input id="paper-pdf-url" v-model="draft.pdf_url" class="input" type="url" maxlength="2048" placeholder="https://" /></div>
            </div>
            <div class="field published-field"><label class="label" for="paper-published">发表时间（可选）</label><input id="paper-published" v-model="draft.published" class="input" maxlength="64" placeholder="例如：2026-10-19" /></div>
          </fieldset>
          <div class="actions"><button class="button primary" :disabled="!!saving">{{ saving === 'import' ? '正在添加…' : '添加论文' }}</button><span class="muted">星号为必填项</span></div>
        </form>
      </section>
    </template>
  </div>
</template>

<style scoped>
.study-selection { display:flex; gap:10px; align-items:center; font-size:13px; color:#677a92; margin-top:14px; }.study-selection input { width:auto; }
.back-link { color: #526581; font-size: .88rem; text-decoration: none; width: fit-content; }
.back-link:hover { color: #245bea; text-decoration: underline; }
.collection-heading-copy { min-width: 0; }
.collection-heading-copy h1 { overflow-wrap: anywhere; }
.collection-description { white-space: pre-wrap; overflow-wrap: anywhere; }
.detail-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 350px); align-items: start; gap: 24px; }
.papers-column, .notes-column { min-width: 0; }
.paper-card h3 { margin: 16px 0 10px; font-size: 1.15rem; line-height: 1.6; overflow-wrap: anywhere; }
.paper-meta { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.paper-external-id { font-size: .75rem; font-family: monospace; overflow-wrap: anywhere; }
.paper-links { font-size: .83rem; margin: 15px 0; }
.paper-links a { color: #245bea; text-underline-offset: 3px; }
.paper-abstract { line-height: 1.85; white-space: pre-wrap; overflow-wrap: anywhere; font-size: .9rem; }
.category-tags { margin: 16px 0; }
.paper-note-form { border-top: 1px solid #dae3ef; padding-top: 20px; margin-top: 20px; }
.personal-paper-editor { border: 1px solid #dae3ef; border-left: 3px solid #245bea; margin-top: 18px; padding: 18px; background: #f4f7fb; }
.personal-paper-editor h4, .personal-paper-editor p { margin: 0; }
.personal-paper-editor .muted { font-size: .83rem; line-height: 1.8; }
.paper-note-form .textarea { margin: 8px 0 12px; }
.paper-note-actions { justify-content: space-between; }
.note-help { font-size: .85rem; line-height: 1.8; }
.metadata-editor summary { cursor: pointer; font-weight: 600; }
.metadata-editor form { padding-top: 20px; }
.import-panel { scroll-margin-top: 20px; }
.import-fields { border: 0; padding: 0; margin: 0; display: grid; gap: 20px; min-width: 0; }
.published-field { max-width: 360px; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
@media (max-width: 1100px) { .detail-layout { grid-template-columns: minmax(0, 1fr); } .notes-column { display: grid; grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 650px) { .paper-note-actions { gap: 12px; } .section-heading { align-items: flex-start; } }
</style>
