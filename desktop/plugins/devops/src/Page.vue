<template>
  <div class="devops-page">
    <header class="header">
      <h1>DevOps 管理</h1>
      <div class="tabs">
        <button :class="['tab', tab === 'projects' && 'active']" @click="tab = 'projects'">📂 项目</button>
        <button :class="['tab', tab === 'terminal' && 'active']" @click="tab = 'terminal'">💻 终端</button>
        <button :class="['tab', tab === 'feishu' && 'active']" @click="tab = 'feishu'">✈️ 飞书</button>
      </div>
    </header>

    <!-- Projects Tab -->
    <div v-if="tab === 'projects'" class="content">
      <div class="toolbar">
        <button class="btn primary" @click="scanProjects">🔍 扫描项目</button>
        <input v-model="projectFilter" class="search-input" placeholder="过滤项目..." />
      </div>
      <div class="project-grid">
        <div v-for="p in filteredProjects" :key="p.path" class="project-card">
          <div class="card-header">
            <span class="card-type">{{ typeIcon(p.type) }}</span>
            <span class="card-name">{{ p.name }}</span>
          </div>
          <div class="card-meta">
            <span>{{ p.type }}</span>
            <span>{{ p.hasGit ? '✓ git' : 'no git' }}</span>
            <span>{{ new Date(p.lastModified).toLocaleDateString() }}</span>
          </div>
          <div class="card-desc">{{ p.description || '暂无描述' }}</div>
          <div class="card-actions">
            <button class="btn sm" @click="openTerminal(p.path, 'opencode')">🚀 opencode</button>
            <button class="btn sm" @click="openTerminal(p.path, 'claude')">🤖 claude</button>
            <button class="btn sm" @click="openFolder(p.path)">📂 文件夹</button>
            <button class="btn sm" @click="openVSCode(p.path)">💻 VS Code</button>
          </div>
        </div>
      </div>
      <div v-if="filteredProjects.length === 0" class="empty">
        <p v-if="projects.length === 0">未找到项目，请点击"扫描项目"</p>
        <p v-else>无匹配项目</p>
      </div>
    </div>

    <!-- Terminal Tab -->
    <div v-if="tab === 'terminal'" class="content">
      <div class="settings-card">
        <h3>终端启动</h3>
        <div class="form-row">
          <label>项目路径</label>
          <input v-model="termProjectPath" class="input" placeholder="选择或输入项目路径..." />
          <button class="btn sm" @click="pickProject">选择</button>
        </div>
        <div class="form-row">
          <label>AI 工具</label>
          <select v-model="termTool" class="input">
            <option value="opencode">opencode</option>
            <option value="claude">claude</option>
          </select>
        </div>
        <div class="form-row">
          <label>提示词 (可选)</label>
          <textarea v-model="termPrompt" class="input" rows="2" placeholder="输入初始提示词..."></textarea>
        </div>
        <button class="btn primary" @click="doLaunchTerminal">🚀 启动终端</button>

        <div v-if="aiResult" class="result-box">
          <h4>AI 响应</h4>
          <pre>{{ aiResult }}</pre>
        </div>
      </div>
    </div>

    <!-- Feishu Tab -->
    <div v-if="tab === 'feishu'" class="content">
      <div class="settings-card">
        <h3>飞书机器人配置</h3>
        <div class="form-row">
          <label>Webhook URL</label>
          <input v-model="feishuCfg.webhookUrl" class="input" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
        </div>
        <div class="form-row">
          <label>签名密钥 (可选)</label>
          <input v-model="feishuCfg.secret" class="input" type="password" placeholder="HMAC-SHA256 签名密钥" />
        </div>
        <div class="form-row">
          <label>启用</label>
          <label class="switch">
            <input type="checkbox" v-model="feishuCfg.enabled" />
            <span class="slider"></span>
          </label>
        </div>
        <button class="btn primary" @click="saveFeishuConfig">💾 保存配置</button>
        <button class="btn" @click="testFeishu">📨 发送测试消息</button>
        <div v-if="feishuStatus" class="status-msg" :class="feishuStatus.ok ? 'ok' : 'err'">{{ feishuStatus.msg }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

defineProps<{ data: any; execute: Function; close: Function }>()

const tab = ref('projects')
const projects = ref<any[]>([])
const projectFilter = ref('')
const termProjectPath = ref('')
const termTool = ref('opencode')
const termPrompt = ref('')
const aiResult = ref('')
const feishuCfg = ref({ webhookUrl: '', secret: '', enabled: false })
const feishuStatus = ref<{ ok: boolean; msg: string } | null>(null)

const filteredProjects = computed(() => {
  if (!projectFilter.value) return projects.value
  const q = projectFilter.value.toLowerCase()
  return projects.value.filter((p: any) => p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q))
})

onMounted(async () => {
  const [proj, cfg] = await Promise.all([
    execute('getProjects'),
    execute('getFeishuConfig'),
  ])
  projects.value = proj || []
  feishuCfg.value = cfg || { webhookUrl: '', secret: '', enabled: false }
})

function typeIcon(type: string) {
  const map: Record<string, string> = { node: '🟢', python: '🐍', rust: '🦀', go: '🔵', dotnet: '🟣', other: '📁' }
  return map[type] || '📁'
}

async function scanProjects() {
  const proj = await execute('scanProjects')
  if (proj) projects.value = proj
}

function pickProject() {
  execute('pickProject').then((path: string) => { if (path) termProjectPath.value = path })
}

function openTerminal(path: string, tool: string) {
  execute('launchTerminal', { path, tool })
}

function openFolder(path: string) {
  execute('openFolder', { path })
}

function openVSCode(path: string) {
  execute('openVSCode', { path })
}

function doLaunchTerminal() {
  execute('launchTerminal', { path: termProjectPath.value, tool: termTool.value, prompt: termPrompt.value })
}

async function saveFeishuConfig() {
  const ok = await execute('saveFeishuConfig', feishuCfg.value)
  feishuStatus.value = ok ? { ok: true, msg: '配置已保存' } : { ok: false, msg: '保存失败' }
  setTimeout(() => { feishuStatus.value = null }, 3000)
}

async function testFeishu() {
  const ok = await execute('testFeishu')
  feishuStatus.value = ok ? { ok: true, msg: '测试消息已发送 ✓' } : { ok: false, msg: '发送失败，请检查配置' }
  setTimeout(() => { feishuStatus.value = null }, 3000)
}
</script>

<style scoped>
.devops-page{padding:20px;font-family:'Segoe UI',sans-serif;color:#333;max-width:1200px;margin:0 auto}
.header{margin-bottom:20px}
.header h1{font-size:20px;font-weight:600;margin:0 0 12px 0}
.tabs{display:flex;gap:4px;border-bottom:1px solid #eee}
.tab{padding:8px 16px;border:none;background:transparent;font-size:13px;color:#666;cursor:pointer;border-bottom:2px solid transparent;transition:all 0.2s}
.tab:hover{color:#333}
.tab.active{color:#409EFF;border-bottom-color:#409EFF}
.content{padding:16px 0}
.toolbar{display:flex;gap:8px;margin-bottom:16px;align-items:center}
.search-input{flex:1;padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:12px;outline:none}
.search-input:focus{border-color:#409EFF}
.project-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.project-card{border:1px solid #eee;border-radius:8px;padding:12px;transition:box-shadow 0.2s}
.project-card:hover{box-shadow:0 2px 12px rgba(0,0,0,0.06)}
.card-header{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.card-type{font-size:16px}
.card-name{font-weight:600;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card-meta{display:flex;gap:12px;font-size:10px;color:#999;margin-bottom:6px}
.card-desc{font-size:11px;color:#666;margin-bottom:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card-actions{display:flex;flex-wrap:wrap;gap:4px}
.btn{padding:6px 12px;border:1px solid #ddd;border-radius:5px;background:#fff;color:#444;font-size:11px;cursor:pointer}
.btn:hover{background:#f5f5f5}
.btn.primary{background:#409EFF;color:#fff;border-color:#409EFF}
.btn.primary:hover{background:#66b1ff}
.btn.sm{padding:4px 8px;font-size:10px}
.empty{text-align:center;padding:40px;color:#999;font-size:13px}
.settings-card{border:1px solid #eee;border-radius:8px;padding:20px;max-width:600px}
.settings-card h3{margin:0 0 16px;font-size:15px}
.form-row{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.form-row label{min-width:80px;font-size:12px;color:#666}
.input{flex:1;padding:7px 10px;border:1px solid #ddd;border-radius:5px;font-size:12px;outline:none}
.input:focus{border-color:#409EFF}
textarea.input{font-family:monospace;resize:vertical}
.result-box{border:1px solid #e0e0e0;border-radius:6px;padding:12px;margin-top:12px;background:#fafafa}
.result-box h4{margin:0 0 8px;font-size:12px;color:#666}
.result-box pre{font-size:11px;white-space:pre-wrap;word-break:break-all;margin:0;color:#333}
.status-msg{padding:8px 12px;border-radius:5px;margin-top:8px;font-size:12px}
.status-msg.ok{background:#e8f5e9;color:#2e7d32}
.status-msg.err{background:#ffebee;color:#c62828}
.switch{position:relative;display:inline-block;width:36px;height:20px}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#ccc;transition:0.3s;border-radius:20px}
.slider::before{content:'';position:absolute;height:16px;width:16px;left:2px;bottom:2px;background:#fff;transition:0.3s;border-radius:50%}
.switch input:checked+.slider{background:#409EFF}
.switch input:checked+.slider::before{transform:translateX(16px)}
</style>
