<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
const auth = useAuthStore(), route = useRoute(), router = useRouter()
const leaving = ref(false), error = ref('')
async function logout() {
  leaving.value = true; error.value = ''
  try { await auth.logout(); await router.push('/login') }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '退出未能完成，请重试。' }
  finally { leaving.value = false }
}
</script>

<template>
  <RouterView v-if="route.path === '/login'" />
  <div v-else class="app-shell">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <aside class="sidebar">
      <RouterLink to="/collections" class="wordmark">Paper<span>Flow</span><i aria-hidden="true">↗</i></RouterLink>
      <p class="sidebar-caption">论文研究工作台</p>
      <nav class="main-nav" aria-label="主要导航">
        <RouterLink to="/papers" :class="{ active: route.path === '/papers' }"><span aria-hidden="true" class="nav-icon">⌕</span>搜索论文<span class="nav-arrow" aria-hidden="true">→</span></RouterLink>
        <RouterLink to="/collections" :class="{ active: route.path.startsWith('/collections') }"><span aria-hidden="true" class="nav-icon">▤</span>我的资料库<span class="nav-arrow" aria-hidden="true">→</span></RouterLink>
        <RouterLink to="/research" :class="{ active: route.path.startsWith('/research') }"><span aria-hidden="true" class="nav-icon">⌁</span>研究任务<span class="nav-arrow" aria-hidden="true">→</span></RouterLink>
        <RouterLink to="/settings" :class="{ active: ['/settings', '/model-settings'].includes(route.path) }"><span aria-hidden="true" class="nav-icon">⚙</span>个人设置<span class="nav-arrow" aria-hidden="true">→</span></RouterLink>
      </nav>
      <div class="sidebar-note"><span class="eyebrow">把思考留在这里</span><p>阅读、记录、连接证据。<br>让想法有处可循。</p></div>
      <div class="account" v-if="auth.user"><RouterLink to="/settings" class="avatar" aria-label="打开个人设置">{{ auth.user.username.slice(0,1).toUpperCase() }}</RouterLink><div class="account-text"><strong>{{ auth.user.username }}</strong><span>{{ auth.user.email }}</span></div><button type="button" class="logout" :disabled="leaving" aria-label="退出登录" @click="logout">{{ leaving ? '…' : '退出' }}</button></div>
    </aside>
    <div class="workspace"><header class="workspace-bar"><span>个人研究空间</span><span class="workspace-caption">让阅读形成积累</span></header><main id="main-content" class="workspace-content"><p v-if="error" class="notice error" role="alert">{{ error }}</p><RouterView :key="route.path" /></main><footer class="workspace-footer">PaperFlow<span>论文 · 证据 · 研究</span></footer></div>
  </div>
</template>
