<template>
  <div class="login-page" @keydown.enter="currentView === 'login' && login()">
    <div class="title-bar">
      <div class="title-left">
        <button class="title-btn" @click="goBack" :style="{ visibility: currentView === 'settings' ? 'visible' : 'hidden' }">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5m7-7-7 7 7 7"/></svg>
        </button>
        <span class="title-text">{{ currentView === 'login' ? 'OmniAide' : '设置' }}</span>
      </div>
      <div class="title-actions">
        <button class="title-btn" @click="goSettings" :style="{ visibility: currentView === 'login' ? 'visible' : 'hidden' }">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06-.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </button>
        <button class="title-btn close-btn" @click="handleClose">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </div>

    <div class="body">
      <div :style="{ display: currentView === 'login' ? '' : 'none' }">
        <el-input v-model="username" placeholder="用户名" style="margin-bottom:12px" />
        <el-input v-model="password" type="password" placeholder="密码" style="margin-bottom:20px" show-password />
        <el-button type="primary" style="width:100%" :loading="loading" @click="login">登录</el-button>
        <p v-if="error" class="error-msg">{{ error }}</p>
      </div>
      <div :style="{ display: currentView === 'settings' ? '' : 'none' }">
        <el-input v-model="serverUrl" placeholder="服务器地址" style="margin-bottom:12px" />
        <p style="font-size:11px;color:#999;margin:0;">重启后生效</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const serverUrl = ref('http://localhost:8000')
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const currentView = ref<'login' | 'settings'>('login')

function goBack() {
  currentView.value = 'login'
  error.value = ''
}
function goSettings() {
  currentView.value = 'settings'
}

async function login() {
  loading.value = true; error.value = ''
  try {
    const res = await fetch(`${serverUrl.value}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value, password: password.value }),
    })
    if (!res.ok) { const d = await res.json(); throw new Error(d.detail || '登录失败') }
    const data = await res.json()
    await window.mqbox.config.set('serverUrl', serverUrl.value)
    await window.mqbox.config.set('token', data.access_token)
    window.mqbox.window.openMain()
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

function handleClose() {
  window.mqbox?.window.quit()
}
</script>

<style scoped>
.login-page { height:100vh; display:flex; flex-direction:column; background:#fff; padding:16px 20px 20px; box-sizing:border-box; }
.title-bar { display:flex; align-items:center; justify-content:space-between; margin-bottom:24px; -webkit-app-region:drag; }
.title-left { display:flex; align-items:center; gap:8px; -webkit-app-region:no-drag; }
.title-text { font-size:18px; font-weight:700; color:#1e1e1e; }
.title-actions { display:flex; gap:6px; -webkit-app-region:no-drag; }
.title-btn { width:28px; height:28px; border-radius:6px; border:none; background:transparent; cursor:pointer; display:flex; align-items:center; justify-content:center; color:#666; flex-shrink:0; }
.title-btn:hover { background:#f0f0f0; }
.close-btn:hover { background:#fee2e2; color:#dc2626; }
.body { flex:1; display:flex; flex-direction:column; justify-content:center; }
.error-msg { color:#f56c6c; font-size:12px; margin:8px 0 0; }
</style>
