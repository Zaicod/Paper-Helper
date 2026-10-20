import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
export const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/', redirect: '/collections' },
  { path: '/login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  { path: '/collections', component: () => import('../views/CollectionsView.vue') },
  { path: '/papers', component: () => import('../views/PaperSearchView.vue') },
  { path: '/collections/:id', component: () => import('../views/CollectionDetailView.vue') },
  { path: '/settings', alias: '/model-settings', component: () => import('../views/ModelSettingsView.vue') },
  { path: '/research', component: () => import('../views/ResearchView.vue') },
  { path: '/research/new', component: () => import('../views/ResearchNewView.vue') },
  { path: '/research/:id', component: () => import('../views/TaskDetailView.vue') },
  { path: '/:pathMatch(.*)*', component: () => import('../views/NotFoundView.vue'), meta: { public: true } },
] })
router.beforeEach(async to => {
  const auth = useAuthStore()
  // A connection failure is shown by the login page; it must not be mistaken for a valid session.
  try { await auth.restore() } catch { if (!to.meta.public) return { path: '/login', query: { redirect: to.fullPath } } }
  if (!to.meta.public && !auth.user) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.path === '/login' && auth.user) return '/collections'
})
