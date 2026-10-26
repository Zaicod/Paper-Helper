<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { Pinia } from 'pinia'
import { getCurrentInstance } from 'vue'
import { api } from '../api'
import type { Paper, PaperDocument } from '../types'
const props = defineProps<{ collectionId: number; paper: Paper }>()
const emit = defineEmits<{ status: [value: PaperDocument | null] }>()
const document = ref<PaperDocument | null>(null)
const busy = ref(false), error = ref('')
const pinia = getCurrentInstance()?.appContext.config.globalProperties.$pinia as Pinia | undefined
const owner = computed(() => pinia?.state.value.auth?.user?.id)
const labels: Record<PaperDocument['status'], string> = {not_prepared:'待准备',ready:'正文已准备',missing:'缺少正文',blocked:'无法访问正文',unreadable:'无法提取正文',timeout:'正文下载超时',unavailable:'正文服务暂不可用'}
let generation = 0
onBeforeUnmount(() => { generation++ })
async function run(operation: () => Promise<PaperDocument>) {
  const active = ++generation
  document.value = null; emit('status', null); busy.value = true; error.value = ''
  try { const result = await operation(); if (active === generation) { document.value = result; emit('status', result) } }
  catch(cause) { if(active === generation) error.value = cause instanceof Error ? cause.message : '正文准备失败，请重试或上传 PDF。' }
  finally { if(active === generation) busy.value = false }
}
watch(() => [props.collectionId, JSON.stringify(props.paper), owner.value], () => { void run(() => api.documents.get(props.collectionId, props.paper.id)) }, {immediate:true, flush:'sync'})
function prepare() { return run(() => api.documents.prepare(props.collectionId, props.paper.id)) }
function check() { return run(() => api.documents.get(props.collectionId, props.paper.id)) }
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]; input.value = ''
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 25 * 1024 * 1024 || file.size === 0) { error.value = '请选择非空的 PDF 文件，大小不超过 25 MiB。'; return }
  await run(() => api.documents.upload(props.collectionId, props.paper.id, file))
}
</script>
<template>
  <div class="paper-document stack" aria-label="论文正文准备">
    <strong role="status">{{ busy ? '正在检查或准备正文…' : document ? labels[document.status] : '正文状态未确认' }}</strong>
    <p v-if="document?.message" class="muted">{{ document.message }}</p>
    <p v-if="document?.status === 'ready'" class="muted">{{ document.filename || '论文 PDF' }} · {{ document.page_count ?? '未知' }} 页 · {{ document.source_kind === 'uploaded' ? '本人上传' : '公开来源' }}</p>
    <p v-if="error" role="alert" class="notice error">{{ error }}</p>
    <div class="actions">
      <button type="button" class="button secondary small" data-test="prepare-document" :disabled="busy" @click="prepare">准备论文正文</button>
      <label class="upload-control">上传已有 PDF<input type="file" accept=".pdf,application/pdf" :disabled="busy" data-test="upload-document" @change="upload"></label>
      <a v-if="document?.status === 'ready' && document.document_id" :href="`/api/library/documents/${encodeURIComponent(document.document_id)}/file`" target="_blank" rel="noopener noreferrer">查看私有 PDF</a>
      <button v-if="error" type="button" class="button secondary small" :disabled="busy" @click="check">重新检查</button>
    </div>
    <small class="muted">找不到公开正文时，可编辑论文资料补充 HTTPS PDF 链接，或上传已有文件。最多 25 MiB、200 页；扫描件与加密文件暂不支持。</small>
  </div>
</template>
<style scoped>
.paper-document {border:1px solid #dae3ef;border-radius:8px;padding:16px;margin:14px 0;gap:10px;min-width:0;overflow-wrap:anywhere}.paper-document p{margin:0}.upload-control{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:13px}.upload-control input{max-width:230px;font-size:12px}.paper-document small{line-height:1.7}
</style>
