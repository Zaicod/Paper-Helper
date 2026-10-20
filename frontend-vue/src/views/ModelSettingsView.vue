<script setup lang="ts">
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import type { ModelProvider, ModelSettings } from '../types'
const defaultProvider = ref<ModelProvider | null>(null)
const auth = useAuthStore()
const selectedDefault = ref<ModelProvider | 'server'>('server')
const savedDefaultModel = ref('')
const loading = ref(true), loaded = ref(false), busy = ref(false), error = ref(''), message = ref('')
const definitions = [{ provider: 'qwen' as const, name: '通义千问 Qwen', preset: 'qwen3.8-flash' }, { provider: 'openai' as const, name: 'OpenAI', preset: 'gpt-5.6-luna' }]
const forms = reactive({
  qwen: { model: 'qwen3.8-flash', key: '', configured: false, hint: '', confirming: false },
  openai: { model: 'gpt-5.6-luna', key: '', configured: false, hint: '', confirming: false },
})
let active = true
function clearSecrets() { for (const item of Object.values(forms)) item.key = '' }
onBeforeUnmount(() => { active = false; clearSecrets() })
function apply(settings: ModelSettings) {
  defaultProvider.value = settings.default_provider
  selectedDefault.value = settings.default_provider || 'server'
  savedDefaultModel.value = settings.providers.find(item => item.provider === settings.default_provider)?.model || ''
  for (const item of settings.providers) {
    const form = forms[item.provider]
    form.model = item.model; form.configured = item.configured; form.hint = item.key_hint || ''; form.confirming = false
  }
}
async function load() {
  loading.value = true; error.value = ''
  try { const settings = await api.modelSettings.get(); if (active) { apply(settings); loaded.value = true } }
  catch { if (active) error.value = '模型设置读取失败，请重试。' }
  finally { if (active) loading.value = false }
}
async function act(operation: () => Promise<unknown>, success: string, reload = true) {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    await operation()
    if (!active) return
    if (success) message.value = success
    if (reload) apply(await api.modelSettings.get())
  } catch { if (active) error.value = '保存失败或操作未完成，请检查模型设置后重试。' }
  finally { if (active) busy.value = false }
}
async function save(provider: ModelProvider) {
  const form = forms[provider]
  const model = form.model.trim(), key = form.key.trim()
  if (!model) { error.value = '请填写默认模型名称。'; return }
  if (!form.configured && !key) { error.value = '首次保存需要填写 API Key。'; return }
  await act(async () => {
    try { await api.modelSettings.save(provider, { model, ...(key ? { api_key: key } : {}) }) }
    finally { form.key = '' }
  }, '模型设置已保存。')
}
async function test(provider: ModelProvider) {
  await act(async () => {
    const result = await api.modelSettings.test(provider)
    if (!active) return
    if (result.success) message.value = result.message || '已保存的配置连接成功。'
    else error.value = result.message || '连接失败，请检查密钥、模型名称和账号权限。'
  }, '', false)
}
function chooseDefault(provider: ModelProvider | null) {
  return act(() => api.modelSettings.setDefault(provider), provider ? '默认提供方已更新。' : '已切换为服务端默认配置。')
}
function saveDefault() {
  return chooseDefault(selectedDefault.value === 'server' ? null : selectedDefault.value)
}
function removeKey(provider: ModelProvider) {
  return act(async () => { await api.modelSettings.removeKey(provider); forms[provider].key = '' }, '密钥已删除。')
}
onMounted(load)
</script>

<template>
  <section class="stack settings-page">
    <div class="page-heading"><div><p class="eyebrow">PERSONAL SETTINGS / 个人设置</p><h1>个人设置</h1><p class="muted">管理当前账号的大模型选择、API 密钥和默认使用方式。</p></div><RouterLink class="button secondary" to="/research/new">新建研究</RouterLink></div>
    <section v-if="auth.user" class="panel account-summary" aria-labelledby="account-heading"><h2 id="account-heading">当前账号</h2><dl><div><dt>用户名</dt><dd>{{ auth.user.username }}</dd></div><div><dt>邮箱</dt><dd>{{ auth.user.email }}</dd></div></dl><p class="muted">以下设置仅用于当前登录账号，不会影响其他用户。</p></section>
    <p class="notice">密钥加密保存在服务端，读取时只显示脱敏提示。密钥留空会保留原值；删除密钥需单独确认。</p>
    <p v-if="loading" role="status" class="muted">正在读取模型设置…</p>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="message" class="notice success" role="status">{{ message }}</p>
    <button v-if="!loaded && !loading" type="button" class="button secondary" @click="load">重新读取</button>
    <template v-if="loaded">
      <section class="panel stack" aria-labelledby="default-heading">
        <div><h2 id="default-heading">默认大模型</h2><p data-test="current-model" class="current-model">当前使用：{{ defaultProvider ? `${defaultProvider === 'qwen' ? '通义千问 Qwen' : 'OpenAI'} · ${savedDefaultModel}` : '服务端配置（环境变量）' }}</p></div>
        <form class="default-form" data-test="default-model-form" @submit.prevent="saveDefault"><label class="field">新任务使用的模型<select v-model="selectedDefault" data-test="default-model-provider" :disabled="busy"><option value="server">服务端配置（使用环境变量）</option><option v-for="item in definitions" :key="item.provider" :value="item.provider" :disabled="!forms[item.provider].configured">{{ item.name }}{{ forms[item.provider].configured ? '' : '（请先在下方保存密钥）' }}</option></select></label><button type="submit" class="button primary" :disabled="busy">保存默认选择</button></form>
        <p class="muted">在下方填写并保存密钥与模型后，在这里选择提供方并保存。新的学习报告和真实研究将使用此选择；已经提交的任务保留原配置。</p>
        <p v-if="!defaultProvider" class="notice">当前没有启用个人模型配置。若提示需要 DASHSCOPE_API_KEY，请先保存下方的个人密钥，再选为默认模型，无需把个人密钥填入环境变量。</p>
      </section>
      <div class="provider-grid">
        <article v-for="item in definitions" :key="item.provider" class="panel stack provider-card" :data-test="`${item.provider}-card`">
          <div class="section-heading"><h2>{{ item.name }}</h2><span v-if="defaultProvider === item.provider" class="tag">当前默认</span></div>
          <p class="credential-state"><span :class="['state-dot', { configured: forms[item.provider].configured }]" aria-hidden="true"></span>{{ forms[item.provider].configured ? '密钥已配置' : '尚未配置密钥' }} <code v-if="forms[item.provider].hint">{{ forms[item.provider].hint }}</code></p>
          <form class="stack" :data-test="`${item.provider}-form`" @submit.prevent="save(item.provider)">
            <label class="field">{{ item.name }} API Key<input v-model="forms[item.provider].key" :data-test="`${item.provider}-key`" type="password" autocomplete="new-password" maxlength="4096" :disabled="busy" :placeholder="forms[item.provider].configured ? '留空保留已保存的密钥' : '输入你的 API Key'"><small>仅在更换密钥时填写，不会回显完整密钥。</small></label>
            <label class="field">{{ item.name }} 默认模型<input v-model="forms[item.provider].model" :data-test="`${item.provider}-model`" :list="`${item.provider}-models`" maxlength="128" required :disabled="busy"><datalist :id="`${item.provider}-models`"><option :value="item.preset" /></datalist><small>可选择预设或手工输入，实际可用性以账号权限和测试结果为准。</small></label>
            <div class="actions"><button type="submit" class="button primary" :data-test="`${item.provider}-save`" :disabled="busy">保存设置</button><button type="button" class="button secondary" :data-test="`${item.provider}-test`" :disabled="busy || !forms[item.provider].configured" @click="test(item.provider)">测试连接</button></div>
          </form>
          <p class="muted test-note">测试使用已保存的密钥和模型，修改后请先保存。会实际调用模型，可能消耗少量额度。</p>
          <div class="provider-tools actions"><button type="button" class="text-button" :data-test="`${item.provider}-default`" :disabled="busy || !forms[item.provider].configured || defaultProvider === item.provider" @click="chooseDefault(item.provider)">设为默认提供方</button><button v-if="forms[item.provider].configured" type="button" class="button small danger" :data-test="`${item.provider}-delete`" :disabled="busy" @click="forms[item.provider].confirming = true">删除密钥</button></div>
          <div v-if="forms[item.provider].confirming" class="notice error stack"><p>确认删除 {{ item.name }} 的密钥？尚未执行的个人模型任务可能失败。</p><div class="actions"><button type="button" class="button danger" :data-test="`${item.provider}-confirm-delete`" :disabled="busy" @click="removeKey(item.provider)">确认删除密钥</button><button type="button" class="button secondary" :disabled="busy" @click="forms[item.provider].confirming = false">取消</button></div></div>
        </article>
      </div>
      <div class="panel server-choice"><div><h2>服务端默认配置</h2><p class="muted">{{ defaultProvider === null ? '当前使用服务端默认配置。' : '也可使用已有的服务端配置创建新任务。' }} 离线演示不调用模型。</p></div><button type="button" class="button secondary" data-test="server-default" :disabled="busy || defaultProvider === null" @click="chooseDefault(null)">使用服务端默认</button></div>
    </template>
  </section>
</template>

<style scoped>
.account-summary h2, #default-heading { margin:0;font-size:18px; }.account-summary dl { display:flex;flex-wrap:wrap;gap:20px 48px;margin:18px 0; }.account-summary dt { color:var(--muted);font-size:12px;margin-bottom:6px; }.account-summary dd { margin:0;overflow-wrap:anywhere; }.account-summary p { margin:0;font-size:12px; }.current-model { font-weight:600;overflow-wrap:anywhere; }.default-form { display:flex;align-items:flex-end;gap:16px; }.default-form .field { flex:1;margin:0; }.default-form button { flex-shrink:0; }@media(max-width:600px){.default-form{align-items:stretch;flex-direction:column}}
.settings-page { max-width: 1120px; }.settings-page > .notice { margin: 0; }.provider-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px; }.provider-card { border-top:3px solid var(--blue); }.section-heading { margin-bottom:0; }.credential-state { display:flex;align-items:center;gap:9px;font-size:12px;margin:0; }.credential-state code { margin-left:auto;color:var(--muted); }.state-dot { width:7px;height:7px;border-radius:50%;background:var(--line); }.state-dot.configured { background:var(--green); }.test-note { font-size:11px;margin:0; }.provider-tools { border-top:1px solid var(--line);padding-top:16px;justify-content:space-between; }.provider-tools .text-button { font-size:12px; }.server-choice { display:flex;align-items:center;justify-content:space-between;gap:20px; }.server-choice h2 { margin:0 0 8px;font-size:16px; }.server-choice p { margin:0;font-size:12px; }.notice p { margin:0; }@media(max-width:1000px){.provider-grid{grid-template-columns:1fr}.server-choice{align-items:flex-start;flex-direction:column}}
</style>
