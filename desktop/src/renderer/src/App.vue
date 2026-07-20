<template>
  <div v-if="ready">
    <MainPanel v-if="view === 'main' && loggedIn" />
    <SearchBox v-else-if="view === 'search' && loggedIn" />
    <PluginPage v-else-if="view === 'plugin-page'" />
    <LoginPage v-else />
  </div>
  <div v-else-if="error" class="error">{{ error }}</div>
  <div v-else class="loading">
    <p>加载中...</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onErrorCaptured } from 'vue'
import MainPanel from './components/MainPanel.vue'
import SearchBox from './components/SearchBox.vue'
import PluginPage from './components/PluginPage.vue'
import LoginPage from './components/LoginPage.vue'

const ready = ref(false)
const loggedIn = ref(false)
const error = ref('')
const params = new URLSearchParams(window.location.search)
const view = ref(params.get('view') || 'main')

onErrorCaptured((err) => {
  error.value = String(err)
  return false
})

onMounted(async () => {
  try {
    let tries = 0
    while (!window.mqbox && tries < 20) {
      await new Promise(r => setTimeout(r, 100))
      tries++
    }
    if (!window.mqbox) { error.value = 'Preload bridge not loaded'; return }
    ready.value = true
    // Check if already logged in
    try {
      const token = await window.mqbox.config.get('token')
      loggedIn.value = !!token
    } catch { loggedIn.value = false }
  } catch (e: any) {
    error.value = String(e)
  }
});

// Expose for LoginPage to call after login
(window as any).setLoggedIn = () => { loggedIn.value = true }
</script>

<style scoped>
.loading { display:flex; align-items:center; justify-content:center; height:100vh; color:#909399; font-size:14px; }
</style>
