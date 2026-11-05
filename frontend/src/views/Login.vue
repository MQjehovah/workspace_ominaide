<template>
  <div class="login-page">
    <div class="login-shell">
      <aside class="brand-panel">
        <div class="brand-top">
          <div class="brand-mark">O</div>
          <span class="brand-name">OmniAide</span>
        </div>
        <div class="brand-copy">
          <h1>你的私有<br />AI 工作台</h1>
          <p>记忆、邮件、日程、笔记与 Coding Agent，全部跑在自己的服务器上。</p>
        </div>
        <ul class="brand-points">
          <li><span class="dot"></span>全栈私有化，数据不出内网</li>
          <li><span class="dot"></span>长期记忆，越用越懂你</li>
          <li><span class="dot"></span>多端同步：Web / 桌面 / 移动</li>
        </ul>
        <div class="brand-foot">MQGEEK · SELF-HOSTED CORE</div>
      </aside>

      <section class="login-card">
        <div class="login-header">
          <h2>欢迎回来</h2>
          <p>登录 OmniAide 管理控制台</p>
        </div>
        <el-form @submit.prevent="handleLogin" class="login-form">
          <el-form-item>
            <el-input v-model="username" placeholder="用户名" prefix-icon="User" size="large" />
          </el-form-item>
          <el-form-item>
            <el-input v-model="password" type="password" placeholder="密码" prefix-icon="Lock" show-password size="large" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" native-type="submit" :loading="loading" size="large" class="login-btn">
              {{ loading ? '登录中...' : '登 录' }}
            </el-button>
          </el-form-item>
        </el-form>
        <p v-if="error" class="error-msg">{{ error }}</p>
        <p class="login-foot">私有部署 · 仅限授权用户访问</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  loading.value = true; error.value = ''
  try {
    await auth.login(username.value, password.value)
    router.push('/')
  } catch (e: any) {
    error.value = e.response?.data?.detail || '登录失败'
  } finally { loading.value = false }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  padding: 28px;
  background:
    radial-gradient(900px 520px at 15% 0%, rgba(99, 102, 241, .28), transparent 60%),
    radial-gradient(800px 480px at 90% 100%, rgba(168, 85, 247, .22), transparent 60%),
    linear-gradient(140deg, #0b1220 0%, #101a30 55%, #0d1526 100%);
  position: relative;
  overflow: hidden;
}
.login-page::before {
  content: '';
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, .035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, .035) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(600px 400px at 30% 30%, #000 20%, transparent 75%);
  pointer-events: none;
}

.login-shell {
  position: relative;
  display: grid; grid-template-columns: 1.05fr .95fr;
  width: min(900px, 100%);
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, .1);
  box-shadow: 0 40px 90px -40px rgba(0, 0, 0, .8);
}

.brand-panel {
  display: flex; flex-direction: column;
  padding: 38px 36px;
  color: #e0e7ff;
  background: linear-gradient(160deg, rgba(79, 70, 229, .32), rgba(15, 23, 42, .55));
  border-right: 1px solid rgba(255, 255, 255, .08);
}
.brand-top { display: flex; align-items: center; gap: 10px; }
.brand-mark {
  width: 34px; height: 34px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; color: #fff;
  background: linear-gradient(135deg, #6366f1, #a855f7);
  box-shadow: 0 10px 24px -10px rgba(99, 102, 241, .9);
}
.brand-name { font-size: 16px; font-weight: 700; letter-spacing: .4px; color: #fff; }
.brand-copy { margin-top: 44px; }
.brand-copy h1 { font-size: 32px; line-height: 1.25; letter-spacing: -.02em; color: #fff; font-weight: 700; }
.brand-copy p { margin-top: 14px; font-size: 13px; line-height: 1.75; color: rgba(224, 231, 255, .68); max-width: 320px; }
.brand-points { list-style: none; margin-top: 34px; display: flex; flex-direction: column; gap: 12px; }
.brand-points li { display: flex; align-items: center; gap: 9px; font-size: 12.5px; color: rgba(224, 231, 255, .78); }
.brand-points .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #818cf8; box-shadow: 0 0 0 3px rgba(129, 140, 248, .16);
  flex-shrink: 0;
}
.brand-foot { margin-top: auto; padding-top: 34px; font-size: 9.5px; letter-spacing: 2px; color: rgba(148, 163, 184, .55); }

.login-card {
  background: rgba(255, 255, 255, .97);
  padding: 44px 40px 34px;
  display: flex; flex-direction: column; justify-content: center;
}
.login-header { margin-bottom: 26px; }
.login-header h2 { font-size: 22px; font-weight: 700; color: #111827; letter-spacing: -.01em; }
.login-header p { margin-top: 6px; font-size: 12.5px; color: #94a3b8; }
.login-form :deep(.el-form-item) { margin-bottom: 16px; }
.login-form :deep(.el-input__wrapper) { border-radius: 9px; padding: 2px 14px; }
.login-form :deep(.el-input__prefix-inner) { color: #94a3b8; }
.login-btn {
  width: 100%; height: 44px; font-size: 14px; border-radius: 9px;
  letter-spacing: 2px; margin-top: 4px;
}
.error-msg { color: #ef4444; text-align: center; font-size: 12.5px; margin: 6px 0 0; }
.login-foot { margin-top: 26px; text-align: center; font-size: 11px; color: #b6bfcd; }

@media (max-width: 820px) {
  .login-shell { grid-template-columns: 1fr; width: min(420px, 100%); }
  .brand-panel { display: none; }
  .login-card { padding: 34px 26px 26px; }
  .login-page { padding: 18px; }
}
</style>
