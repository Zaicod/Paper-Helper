<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
const auth = useAuthStore(), router = useRouter(), route = useRoute()
const registering = ref(false), busy = ref(false), error = ref(''), showPassword = ref(false)
const identifier = ref(''), username = ref(''), email = ref(''), password = ref('')
function switchMode() { registering.value = !registering.value; error.value = ''; password.value = '' }
async function submit() {
  if (busy.value) return
  error.value = ''; busy.value = true
  try {
    if (new TextEncoder().encode(password.value).length > 72) throw new Error('密码过长，请控制在 72 个 UTF-8 字节内。')
    if (registering.value) await auth.register({ username: username.value.trim(), email: email.value.trim(), password: password.value })
    else await auth.login({ identifier: identifier.value.trim(), password: password.value })
    password.value = ''
    const target = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    await router.push(target.startsWith('/') && !target.startsWith('//') && !target.includes('\\') ? target : '/collections')
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '操作未能完成，请重试。' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="login-page">
    <section class="login-intro" aria-label="PaperFlow 论文研究工作台">
      <a class="login-wordmark" href="/">Paper<span>Flow</span><i aria-hidden="true">↗</i></a>
      <div class="login-story"><span class="eyebrow">论文研究工作台</span><h1>从一篇论文，<br>走向一个<br><em>研究问题。</em></h1><p>整理阅读材料，留下思考，<br>让每一次研究都有迹可循。</p></div>
      <div class="reading-mark"><span aria-hidden="true">文献 → 证据 → 思考</span><p>把阅读积累成自己的研究脉络。</p></div>
    </section>
    <main class="login-main">
      <div class="login-card">
        <span class="eyebrow">你的研究，从这里继续</span>
        <h2>{{ registering ? '创建你的工作台' : '欢迎回来' }}</h2>
        <p class="muted">{{ registering ? '建立账号，保存论文、笔记与研究记录。' : '登录后查看你的论文资料与研究进展。' }}</p>
        <form class="stack" @submit.prevent="submit">
          <template v-if="registering">
            <label class="field">用户名<input v-model="username" name="username" required minlength="3" maxlength="64" autocomplete="username" placeholder="至少 3 个字符"></label>
            <label class="field">邮箱<input v-model="email" name="email" type="email" required maxlength="320" autocomplete="email" placeholder="you@example.com"></label>
          </template>
          <label v-else class="field">用户名或邮箱<input v-model="identifier" name="identifier" required maxlength="320" autocomplete="username" placeholder="输入用户名或邮箱"></label>
          <label class="field">密码<span class="password-field"><input v-model="password" name="password" :type="showPassword ? 'text' : 'password'" required :minlength="registering ? 8 : 1" maxlength="128" :autocomplete="registering ? 'new-password' : 'current-password'" :placeholder="registering ? '至少 8 个字符' : '输入密码'"><button type="button" class="text-button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</button></span></label>
          <p v-if="error" role="alert" class="notice error">{{ error }}</p>
          <button class="button primary login-submit" :disabled="busy" type="submit">{{ busy ? '请稍候…' : registering ? '注册并进入工作台' : '登录工作台' }}<span aria-hidden="true">→</span></button>
        </form>
        <p class="switch-auth">{{ registering ? '已有账号？' : '还没有账号？' }}<button type="button" class="text-button" :disabled="busy" @click="switchMode">{{ registering ? '返回登录' : '创建账号' }}</button></p>
        <p class="login-footnote">使用新工作台账号登录。旧版页面的账号与资料尚未迁移。</p>
      </div>
    </main>
  </div>
</template>

<style scoped>
.login-page{min-height:100vh;display:grid;grid-template-columns:47% 53%;background:white}.login-intro{background:var(--ink);color:white;padding:46px 10%;display:flex;flex-direction:column;justify-content:space-between;min-height:100vh}.login-wordmark{font:600 31px Georgia,serif;letter-spacing:-1px;color:white;text-decoration:none}.login-wordmark span{font-weight:400}.login-wordmark i{font:25px var(--font-body);margin-left:12px;color:#8eafff}.login-story{padding:64px 0}.login-story .eyebrow{color:#a8c2ff}.login-story h1{font-size:clamp(36px,4vw,62px);line-height:1.35;font-weight:500;letter-spacing:-2px;margin:22px 0}.login-story em{font-style:normal;color:#a8c2ff}.login-story p{color:#becbdd;line-height:1.9}.reading-mark{border-top:1px solid #ffffff30;padding-top:22px;color:#dce6f5;font-size:13px;letter-spacing:2px}.reading-mark p{color:#92a5c0;letter-spacing:0;font-size:12px}.login-main{display:grid;place-items:center;padding:50px 30px}.login-card{max-width:390px;width:100%}.login-card h2{font-size:30px;letter-spacing:-1px;margin:14px 0}.login-card form{margin-top:32px}.password-field{display:flex;position:relative}.password-field input{padding-right:62px}.password-field button{position:absolute;right:12px;top:10px;font-size:12px}.login-submit{width:100%;justify-content:space-between;margin-top:5px}.switch-auth{text-align:center;font-size:13px;margin-top:23px}.switch-auth button{margin-left:6px}.login-footnote{font-size:11px;line-height:1.8;color:var(--muted);border-top:1px solid var(--line);padding-top:20px;margin-top:32px}@media(max-width:760px){.login-page{grid-template-columns:1fr}.login-intro{min-height:auto;padding:24px}.login-story{padding:20px 0 10px}.login-story h1{font-size:30px;letter-spacing:0}.login-story h1 br{display:none}.login-story p,.reading-mark{display:none}.login-main{padding:35px 24px}.login-card{max-width:440px}}
</style>
