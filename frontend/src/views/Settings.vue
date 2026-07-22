<template>
  <div class="page-wrapper">
    <div class="page-header"><h2>设置</h2></div>
    <div class="page-card">
      <div class="page-card-body">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="个人资料" name="profile">
            <el-form v-if="profileForm" label-width="120px" style="margin-top:12px;max-width:600px">
              <el-form-item label="用户名">
                <el-input :model-value="auth.user?.username" disabled />
              </el-form-item>
              <el-form-item label="邮箱">
                <el-input :model-value="auth.user?.email" disabled />
              </el-form-item>
              <el-divider />
              <el-form-item label="姓名">
                <el-input v-model="profileForm.name" placeholder="您的姓名" />
              </el-form-item>
              <el-form-item label="身份/职位">
                <el-input v-model="profileForm.role" placeholder="如：产品经理、设计师" />
              </el-form-item>
              <el-form-item label="公司/组织">
                <el-input v-model="profileForm.company" placeholder="公司或组织名称" />
              </el-form-item>

              <el-form-item label="联系人">
                <div style="width:100%">
                  <div v-for="(c, i) in profileForm.contacts" :key="i" style="display:flex;gap:8px;margin-bottom:8px">
                    <el-input v-model="c.name" placeholder="姓名" style="flex:1" />
                    <el-input v-model="c.relation" placeholder="关系" style="flex:1" />
                    <el-button type="danger" :icon="Delete" @click="removeContact(i)" />
                  </div>
                  <el-button type="primary" link @click="addContact">+ 添加联系人</el-button>
                </div>
              </el-form-item>

              <el-form-item label="项目">
                <div style="width:100%">
                  <div v-for="(p, i) in profileForm.projects" :key="i" style="display:flex;gap:8px;margin-bottom:8px">
                    <el-input v-model="p.name" placeholder="项目名称" style="flex:1" />
                    <el-input v-model="p.deadline" placeholder="截止日期" style="flex:1" />
                    <el-button type="danger" :icon="Delete" @click="removeProject(i)" />
                  </div>
                  <el-button type="primary" link @click="addProject">+ 添加项目</el-button>
                </div>
              </el-form-item>

              <el-form-item>
                <el-button type="primary" :loading="saving" @click="saveProfile">保存资料</el-button>
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
import { ref, reactive, onMounted } from 'vue'
import client from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'

const activeTab = ref('profile')
const auth = useAuthStore()
const saving = ref(false)

interface Contact { name: string; relation: string }
interface Project { name: string; deadline: string }

const profileForm = ref<{
  name: string; role: string; company: string
  contacts: Contact[]; projects: Project[]
} | null>(null)

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

async function fetchProfile() {
  try {
    const res = await client.get('/auth/profile')
    const d = res.data
    profileForm.value = {
      name: d.name || '',
      role: d.role || '',
      company: d.company || '',
      contacts: d.contacts || [],
      projects: d.projects || [],
    }
  } catch { /* ignore */ }
}

function addContact() {
  profileForm.value!.contacts.push({ name: '', relation: '' })
}

function removeContact(i: number) {
  profileForm.value!.contacts.splice(i, 1)
}

function addProject() {
  profileForm.value!.projects.push({ name: '', deadline: '' })
}

function removeProject(i: number) {
  profileForm.value!.projects.splice(i, 1)
}

async function saveProfile() {
  saving.value = true
  try {
    await client.put('/auth/profile', profileForm.value)
    ElMessage.success('资料已保存')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    await auth.fetchUser()
  } catch { /* ignore */ }
  fetchProfile()
  checkHealth()
})
</script>
