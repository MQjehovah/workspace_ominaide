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

          <el-tab-pane label="开发者档案" name="developer">
            <el-form v-if="profileForm" label-width="130px" style="margin-top:12px;max-width:640px">
              <el-form-item label="GitHub 用户名">
                <el-input v-model="profileForm.developer.github_username" placeholder="MQjehovah" />
              </el-form-item>
              <el-form-item label="Git 提交邮箱">
                <el-input v-model="profileForm.developer.github_email" placeholder="you@example.com" />
              </el-form-item>
              <el-form-item label="默认组织">
                <el-input v-model="profileForm.developer.default_org" placeholder="可选" />
              </el-form-item>
              <el-form-item label="默认分支">
                <el-input v-model="profileForm.developer.default_branch" placeholder="main" />
              </el-form-item>
              <el-form-item label="工作区根目录">
                <el-input v-model="workspaceRootsText" type="textarea" :rows="3" placeholder="每行一个路径，例如 E:\workspace" />
              </el-form-item>
              <el-form-item label="认证方式">
                <el-radio-group v-model="profileForm.developer.auth">
                  <el-radio-button value="ssh">SSH key</el-radio-button>
                  <el-radio-button value="gh">gh CLI</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="SSH key 路径">
                <el-input v-model="profileForm.developer.ssh_key_path" placeholder="~/.ssh/id_rsa" />
              </el-form-item>
              <el-form-item label="允许的操作">
                <el-checkbox-group v-model="profileForm.developer.permissions">
                  <el-checkbox value="read">读取</el-checkbox>
                  <el-checkbox value="edit">修改</el-checkbox>
                  <el-checkbox value="commit">提交</el-checkbox>
                  <el-checkbox value="push">推送</el-checkbox>
                  <el-checkbox value="pr">开 PR</el-checkbox>
                </el-checkbox-group>
              </el-form-item>
              <el-form-item label="提交规范">
                <el-input v-model="profileForm.developer.commit_style" placeholder="例如：类型: 简短描述" />
              </el-form-item>
              <el-form-item label="补充说明">
                <el-input v-model="profileForm.developer.notes" type="textarea" :rows="2" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="saving" @click="saveProfile">保存档案</el-button>
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
              <el-form-item label="调用方式">
                <el-radio-group v-model="llmConfig.mode">
                  <el-radio-button value="backend">后端代理</el-radio-button>
                  <el-radio-button value="direct">前端直连</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="API Key">
                <el-input v-model="llmConfig.apiKey" type="password" show-password placeholder="sk-..." />
              </el-form-item>
              <el-form-item label="API 地址">
                <el-input v-model="llmConfig.baseUrl" placeholder="https://api.openai.com/v1" />
              </el-form-item>
              <el-form-item label="模型">
                <el-input v-model="llmConfig.model" placeholder="gpt-4o-mini" />
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
interface Developer {
  github_username: string; github_email: string; default_org: string
  workspace_roots: string[]; default_branch: string; auth: string
  ssh_key_path: string; permissions: string[]; commit_style: string; notes: string
}

const workspaceRootsText = ref('')

const profileForm = ref<{
  name: string; role: string; company: string
  contacts: Contact[]; projects: Project[]; developer: Developer
} | null>(null)

function emptyDeveloper(): Developer {
  return {
    github_username: '',
    github_email: '',
    default_org: '',
    workspace_roots: [],
    default_branch: 'main',
    auth: 'ssh',
    ssh_key_path: '',
    permissions: ['read', 'edit', 'commit', 'push'],
    commit_style: '',
    notes: '',
  }
}

const connected = ref(false)
const serverVersion = ref('')

const serverUrl = ref(localStorage.getItem('server_url') || 'http://localhost:8000')

function saveServerUrl() {
  localStorage.setItem('server_url', serverUrl.value)
  ElMessage.success('已保存')
}

const llmConfig = ref({
  apiKey: '',
  baseUrl: 'https://api.openai.com/v1',
  model: 'gpt-4o-mini',
  mode: 'backend' as 'backend' | 'direct'
})

function loadLlmConfig() {
  try {
    const raw = localStorage.getItem('ai_chat_config')
    if (raw) {
      const parsed = JSON.parse(raw)
      llmConfig.value = {
        apiKey: parsed.apiKey || '',
        baseUrl: parsed.baseUrl || 'https://api.openai.com/v1',
        model: parsed.model || 'gpt-4o-mini',
        mode: parsed.mode === 'direct' ? 'direct' : 'backend'
      }
      return
    }
  } catch { /* ignore */ }
  llmConfig.value.apiKey = localStorage.getItem('llm_api_key') || ''
  llmConfig.value.baseUrl = localStorage.getItem('llm_base_url') || 'https://api.openai.com/v1'
  llmConfig.value.model = localStorage.getItem('llm_model') || 'gpt-4o-mini'
}

function saveLlmConfig() {
  localStorage.setItem('ai_chat_config', JSON.stringify(llmConfig.value))
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
    const dev = d.developer || {}
    profileForm.value = {
      name: d.name || '',
      role: d.role || '',
      company: d.company || '',
      contacts: d.contacts || [],
      projects: d.projects || [],
      developer: {
        ...emptyDeveloper(),
        ...dev,
        workspace_roots: dev.workspace_roots || [],
        permissions: dev.permissions || ['read', 'edit', 'commit', 'push'],
      },
    }
    workspaceRootsText.value = (dev.workspace_roots || []).join('\n')
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
    const payload: any = {
      ...profileForm.value,
      developer: {
        ...profileForm.value!.developer,
        workspace_roots: workspaceRootsText.value.split('\n').map(s => s.trim()).filter(Boolean),
      },
    }
    await client.put('/auth/profile', payload)
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
  loadLlmConfig()
})
</script>
