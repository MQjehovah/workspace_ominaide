<template>
  <div class="page-wrapper">
    <div class="page-header"><h2>设置</h2></div>
    <div class="page-card">
      <div class="page-card-body">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="个人资料" name="profile">
            <el-form v-if="profile" label-width="120px" style="margin-top:12px;max-width:600px">
              <el-form-item label="用户名">
                <el-input :model-value="profile.username" disabled />
              </el-form-item>
              <el-form-item label="邮箱">
                <el-input :model-value="profile.email" disabled />
              </el-form-item>
            </el-form>
            <p v-else style="color:#909399;padding:20px">加载中...</p>
          </el-tab-pane>

          <el-tab-pane label="服务器" name="server">
            <el-form label-width="120px" style="margin-top:12px;max-width:600px">
              <el-form-item label="服务器地址">
                <el-input v-model="serverUrl" placeholder="http://localhost:8000" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="saveServerUrl">保存</el-button>
              </el-form-item>
              <el-form-item label="连接状态">
                <el-tag :type="connected ? 'success' : 'danger'">{{ connected ? '已连接' : '未连接' }}</el-tag>
              </el-form-item>
              <el-form-item label="后端版本">
                <span>{{ serverVersion || '-' }}</span>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="LLM" name="llm">
            <el-form label-width="120px" style="margin-top:12px;max-width:600px">
              <el-form-item label="API Key">
                <el-input v-model="llmConfig.apiKey" type="password" show-password placeholder="sk-..." />
              </el-form-item>
              <el-form-item label="API 地址">
                <el-input v-model="llmConfig.baseUrl" placeholder="https://api.openai.com/v1" />
              </el-form-item>
              <el-form-item label="模型">
                <el-input v-model="llmConfig.model" placeholder="gpt-4o" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="saveLlmConfig">保存</el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const activeTab = ref('profile')
const auth = useAuthStore()
const profile = ref<any>(null)

const connected = ref(false)
const serverVersion = ref('')

const serverUrl = ref(localStorage.getItem('server_url') || 'http://localhost:8000')

const llmConfig = ref({
  apiKey: localStorage.getItem('llm_api_key') || '',
  baseUrl: localStorage.getItem('llm_base_url') || 'https://api.openai.com/v1',
  model: localStorage.getItem('llm_model') || 'gpt-4o'
})

function saveServerUrl() {
  localStorage.setItem('server_url', serverUrl.value)
  ElMessage.success('已保存')
}

function saveLlmConfig() {
  localStorage.setItem('llm_api_key', llmConfig.value.apiKey)
  localStorage.setItem('llm_base_url', llmConfig.value.baseUrl)
  localStorage.setItem('llm_model', llmConfig.value.model)
  ElMessage.success('已保存')
}

async function checkHealth() {
  try {
    const res = await client.get('/health')
    connected.value = true
    serverVersion.value = res.data.version || ''
  } catch {
    connected.value = false
  }
}

onMounted(async () => {
  try {
    await auth.fetchUser()
    profile.value = auth.user
  } catch { /* ignore */ }
  checkHealth()
})
</script>
