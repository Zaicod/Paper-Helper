import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { useAuthStore } from './stores/auth'
import { setUnauthorizedHandler } from './api/http'
import './style.css'
const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
setUnauthorizedHandler(() => { useAuthStore(pinia).clear(); if (router.currentRoute.value.path !== '/login') void router.replace('/login') })
app.use(router)
app.mount('#app')
