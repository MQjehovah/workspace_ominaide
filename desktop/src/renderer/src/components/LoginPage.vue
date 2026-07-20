<template>
  <div class="login-page" @keydown.enter="login">
    <div class="login-card">
      <h2>OmniAide</h2>
      <el-input v-model="serverUrl" placeholder="服务器地址" style="margin-bottom:12px" />
      <el-input v-model="username" placeholder="用户名" style="margin-bottom:12px" />
      <el-input v-model="password" type="password" placeholder="密码" style="margin-bottom:20px" show-password />
      <el-button type="primary" style="width:100%" :loading="loading" @click="login">登录</el-button>
      <p v-if="error" style="color:#f56c6c;font-size:12px;margin-top:8px">{{ error }}</p>
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
    // Switch to main view without reload
    if ((window as any).setLoggedIn) (window as any).setLoggedIn()
    window.history.replaceState(null, '', '?view=main')
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}
</script>

<style scoped>
.login-page { height:100vh; display:flex; align-items:center; justify-content:center; background:#f5f7fa; }
.login-card { width:340px; padding:32px; background:#fff; border-radius:12px; box-shadow:0 2px 12px rgba(0,0,0,0.08); }
.login-card h2 { text-align:center; margin-bottom:24px; font-size:22px; }
</style>
