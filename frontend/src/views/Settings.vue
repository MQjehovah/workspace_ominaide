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

          <el-tab-pane label="连接器" name="connectors">
            <div style="margin-top:12px;max-width:720px">
              <div v-for="p in connectors" :key="p.key" class="connector-card">
                <div class="connector-head">
                  <div>
                    <strong>{{ p.name }}</strong>
                    <el-tag size="small" :type="p.configured ? 'success' : 'info'" style="margin-left:8px">
                      {{ p.configured ? '已配置' : '未配置' }}
                    </el-tag>
                  </div>
                  <el-button
                    v-if="p.configured"
                    size="small"
                    type="primary"
                    :loading="connectorLoading"
                    @click="connectProvider(p.key)"
                  >
                    连接账号
                  </el-button>
                </div>
                <div class="muted">{{ p.description }}</div>
                <div v-if="!p.configured" class="connector-hint">
                  服务端需要配置 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET。
                </div>
                <div v-else-if="p.accounts.length" class="connector-accounts">
                  <div v-for="a in p.accounts" :key="a.id" class="connector-account">
                    <span>{{ a.email || a.name || a.account_id }}</span>
                    <el-button size="small" text type="danger" @click="disconnectConnector(a.id)">断开</el-button>
                  </div>
                </div>
                <div v-else-if="p.configured" class="connector-hint">还没有连接账号。</div>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="钉钉" name="dingtalk">
            <el-form label-width="120px" style="margin-top:12px;max-width:680px">
              <el-form-item label="连接状态">
                <el-tag :type="dingtalk.authenticated ? 'success' : 'info'">
                  {{ dingtalk.authenticated ? '已绑定' : '未绑定' }}
                </el-tag>
                <span v-if="dingtalk.error" style="margin-left:10px;color:#f56c6c;font-size:12px">
                  {{ dingtalk.error }}
                </span>
              </el-form-item>
              <el-form-item label="我的目录">
                <el-input :model-value="dingtalk.dingtalk_dir" disabled />
              </el-form-item>
              <el-form-item label="钉钉账号">
                <div style="width:100%">
                  <div v-if="dingtalkLogin && dingtalkLogin.status === 'pending'">
                    <p style="margin:0 0 8px">
                      请在钉钉中打开下面的链接，或输入授权码
                      <strong style="font-size:16px;margin-left:6px">{{ dingtalkLogin.user_code }}</strong>
                    </p>
                    <el-link
                      v-if="dingtalkLogin.verification_url"
                      :href="dingtalkLogin.verification_url"
                      target="_blank"
                      type="primary"
                    >
                      {{ dingtalkLogin.verification_url }}
                    </el-link>
                    <p style="color:#909399;font-size:12px;margin:8px 0 0">
                      等待授权中，完成后会自动刷新（{{ dingtalkLogin.expires_in }} 秒内有效）
                    </p>
                  </div>
                  <div v-else>
                    <el-button type="primary" :loading="dingtalkStarting" @click="startDingtalkLogin">
                      {{ dingtalk.authenticated ? '重新绑定钉钉' : '绑定我的钉钉' }}
                    </el-button>
                    <el-button v-if="dingtalk.authenticated" @click="logoutDingtalk">解绑</el-button>
                  </div>
                </div>
              </el-form-item>
              <el-form-item label="当前账号">
                <pre style="margin:0;max-height:220px;overflow:auto;font-size:12px">{{ dingtalkStatusText }}</pre>
              </el-form-item>
            </el-form>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
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

const dingtalk = ref<any>({
  configured: false,
  authenticated: false,
  status: {},
  error: null,
  dingtalk_dir: '',
})
const dingtalkLogin = ref<any>(null)
const dingtalkStarting = ref(false)
let dingtalkTimer: number | undefined

const dingtalkStatusText = computed(() =>
  JSON.stringify(dingtalk.value.status || {}, null, 2)
)

async function fetchDingtalkStatus() {
  try {
    const res = await client.get('/dingtalk/status')
    dingtalk.value = res.data
  } catch (e: any) {
    dingtalk.value.error = e.response?.data?.detail || '无法读取钉钉状态'
  }
}

async function pollDingtalkLogin() {
  try {
    const res = await client.get('/dingtalk/login/status')
    dingtalkLogin.value = res.data
    if (res.data.status === 'authorized') {
      stopDingtalkPolling()
      ElMessage.success('钉钉绑定成功')
      await fetchDingtalkStatus()
    } else if (res.data.status === 'failed') {
      stopDingtalkPolling()
      ElMessage.error(res.data.error || '钉钉绑定失败')
    }
  } catch { /* keep polling */ }
}

function stopDingtalkPolling() {
  if (dingtalkTimer) {
    window.clearInterval(dingtalkTimer)
    dingtalkTimer = undefined
  }
}

async function startDingtalkLogin() {
  dingtalkStarting.value = true
  try {
    const res = await client.post('/dingtalk/login/start', {})
    dingtalkLogin.value = res.data
    stopDingtalkPolling()
    dingtalkTimer = window.setInterval(pollDingtalkLogin, 2500)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '启动钉钉登录失败')
  } finally {
    dingtalkStarting.value = false
  }
}

async function logoutDingtalk() {
  try {
    await client.post('/dingtalk/logout', {})
    dingtalkLogin.value = null
    stopDingtalkPolling()
    ElMessage.success('已解绑钉钉')
    await fetchDingtalkStatus()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '解绑失败')
  }
}

const connectors = ref<any[]>([])
const connectorLoading = ref(false)

async function fetchConnectors() {
  try {
    const res = await client.get('/connectors')
    connectors.value = res.data?.providers || []
  } catch {
    connectors.value = []
  }
}

async function connectProvider(provider: string) {
  connectorLoading.value = true
  try {
    const res = await client.post('/connectors/oauth/start', { provider })
    const url = res.data?.auth_url
    if (!url) throw new Error('未拿到授权地址')
    window.location.href = url
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || e.message || '连接失败')
  } finally {
    connectorLoading.value = false
  }
}

async function disconnectConnector(id: number) {
  try {
    await client.delete(`/connectors/${id}`)
    ElMessage.success('已断开连接')
    await fetchConnectors()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '断开失败')
  }
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
  fetchDingtalkStatus()
  await fetchConnectors()
  const params = new URLSearchParams(window.location.search)
  const tab = params.get('tab')
  if (tab) activeTab.value = tab
  const connector = params.get('connector')
  if (connector) {
    if (params.get('status') === 'ok') {
      ElMessage.success(`${connector} 连接成功`)
    } else if (params.get('status') === 'error') {
      ElMessage.error(params.get('message') || '连接失败')
    }
    window.history.replaceState({}, '', window.location.pathname)
  }
})

onUnmounted(() => {
  stopDingtalkPolling()
})
</script>
