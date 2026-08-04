<template>
  <div class="devops-page">
    <header class="header">
      <h1>DevOps 管理</h1>
      <div class="tabs">
        <button :class="['tab', tab === 'projects' && 'active']" @click="tab = 'projects'">📂 项目</button>
        <button :class="['tab', tab === 'channels' && 'active']" @click="tab = 'channels'">🔌 通道</button>
      </div>
    </header>

    <!-- Projects Tab -->
    <div v-if="tab === 'projects'" class="content">
      <div class="toolbar">
        <button class="btn primary" @click="pickAndScan">🔍 扫描目录</button>
        <button class="btn" @click="addProjectDir">➕ 添加项目</button>
        <input v-model="projectFilter" class="search-input" placeholder="过滤项目..." />
      </div>
      <div class="project-grid scrollable">
        <div v-for="p in filteredProjects" :key="p.path" class="project-card">
          <div class="card-header">
            <span class="card-type">{{ typeIcon(p.type) }}</span>
            <span class="card-name">{{ p.name }}</span>
            <span v-if="binding === p.path" class="bound-badge">📌 已绑定飞书</span>
          </div>
          <div class="card-meta">
            <span>{{ p.type }}</span>
            <span>{{ new Date(p.lastModified).toLocaleDateString() }}</span>
          </div>
          <div class="card-desc">{{ p.description || p.path }}</div>
          <div class="card-actions">
            <select v-model="toolSelMap[p.path]" class="tool-select" title="选择代理 AI 工具">
              <option value="opencode">opencode</option>
              <option value="claude">claude</option>
              <option value="codex">codex</option>
            </select>
            <button
              v-if="!isAgentActive(p)"
              class="btn sm accent"
              @click="startAgent(p)"
              :disabled="!!agentRunning"
            >
              {{ agentRunning === p.path ? '⏳ 启动中...' : '▶ 启动' }}
            </button>
            <button v-else class="btn sm danger" @click="stopAgent(p)" :disabled="!!agentRunning">
              {{ agentRunning === p.path ? '⏳ 停止中...' : '■ 停止' }}
            </button>
            <button class="btn sm" @click="bindFeishu(p)">📌 绑定飞书</button>
            <button class="btn sm" @click="openFolder(p.path)">📂 文件夹</button>
            <button class="btn sm" @click="openVSCode(p.path)">💻 VS Code</button>
            <button class="btn sm" @click="removeProject(p)">🗑 移除</button>
          </div>
          <div v-if="agentResult && agentResultPath === p.path" class="agent-result" :class="agentResult.ok ? 'ok' : 'err'">
            <div class="agent-result-head">{{ agentResult.ok ? '✅ 已启动' : '❌ 启动失败' }} · {{ agentResult.tool }} · {{ agentResult.ms }}ms</div>
            <pre>{{ agentResult.output }}</pre>
          </div>
        </div>
      </div>
      <div v-if="filteredProjects.length === 0" class="empty">
        <p v-if="projects.length === 0">未找到项目，请点击"扫描项目"</p>
        <p v-else>无匹配项目</p>
      </div>
    </div>

    <!-- Channels Tab -->
    <div v-if="tab === 'channels'" class="content">
      <div class="toolbar">
        <button class="btn primary" @click="openAddChannel">➕ 新增通道</button>
        <button class="btn" @click="loadChannels">🔄 刷新</button>
      </div>

      <div class="channel-list">
        <div v-for="c in channels" :key="c.id" class="channel-card">
          <div class="card-header">
            <span class="card-type">{{ channelIcon(c.type) }}</span>
            <span class="card-name">{{ c.name }}</span>
            <span class="channel-state" :class="statusOf(c.id)?.status">{{ statusLabel(statusOf(c.id)?.status) }}</span>
          </div>
          <div class="card-meta">
            <span>{{ channelTypeLabel(c.type) }}</span>
            <label class="switch">
              <input type="checkbox" :checked="c.enabled" @change="toggleChannel(c, ($event.target as HTMLInputElement).checked)" />
              <span class="slider"></span>
            </label>
            <span>启用</span>
          </div>
          <div class="channel-fields">
            <template v-if="c.type === 'feishu'">
              <div class="form-row"><label>App ID</label><input v-model="c.config.appId" class="input" placeholder="飞书开放平台 App ID" /></div>
              <div class="form-row"><label>App Secret</label><input v-model="c.config.appSecret" class="input" type="password" placeholder="App Secret" /></div>
            </template>
            <template v-else-if="c.type === 'telegram'">
              <div class="form-row"><label>Bot Token</label><input v-model="c.config.botToken" class="input" placeholder="Telegram Bot Token (from @BotFather)" /></div>
            </template>
            <template v-else-if="c.type === 'webhook'">
              <div class="form-row"><label>端口</label><input v-model.number="c.config.port" class="input" placeholder="本地监听端口，默认 8841" /></div>
              <div class="form-row"><label>回调 URL</label><input v-model="c.config.callbackUrl" class="input" placeholder="可选：POST 回复到此 URL" /></div>
              <div class="card-hint">POST 到 http://127.0.0.1:{c.config.port || 8841}/，JSON: {"text": "..."}</div>
            </template>
          </div>
          <div class="card-actions">
            <button class="btn sm primary" @click="saveChannel(c)">💾 保存</button>
            <button class="btn sm" @click="testChannel(c)">📨 测试</button>
            <button class="btn sm danger" @click="removeChannel(c)">🗑 删除</button>
          </div>
        </div>
        <div v-if="channels.length === 0" class="empty">暂无通道，点击"➕ 新增通道"</div>
      </div>

      <!-- Add channel modal -->
      <div v-if="showAddModal" class="ql-mask" @click.self="showAddModal = false">
        <div class="ql-editor">
          <h3>新增通道</h3>
          <div class="type-row">
            <button v-for="t in channelTypes" :key="t.type" class="type-btn" :class="{ active: newChannel.type === t.type }" @click="newChannel.type = t.type">
              {{ channelIcon(t.type) }} {{ t.label }}
            </button>
          </div>
          <p class="card-hint" v-if="channelTypes.find(t => t.type === newChannel.type)">{{ channelTypes.find(t => t.type === newChannel.type)?.desc }}</p>
          <label class="fld">名称</label>
          <input v-model="newChannel.name" class="inp" placeholder="例如：飞书 1 / Telegram" />
          <div class="ed-actions">
            <button class="btn ghost" @click="showAddModal = false">取消</button>
            <button class="btn primary" @click="addChannel">创建</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const { execute } = defineProps<{ data: any; execute: Function; close: Function }>()

const tab = ref('projects')
const projects = ref<any[]>([])
const projectFilter = ref('')
const toolSelMap = ref<Record<string, string>>({})
const agentRunning = ref('')
const agentResult = ref<any>(null)
const agentResultPath = ref('')
const activeAgent = ref<{ path: string; tool: string } | null>(null)
const binding = ref('')
const channels = ref<any[]>([])
const channelTypes = ref<any[]>([])
const channelStatus = ref<any[]>([])
const showAddModal = ref(false)
const newChannel = ref<{ type: string; name: string }>({ type: 'feishu', name: '' })
let statusPollTimer: any = null

const filteredProjects = computed(() => {
  if (!projectFilter.value) return projects.value
  const q = projectFilter.value.toLowerCase()
  return projects.value.filter((p: any) => p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q))
})

function statusOf(id: string) {
  return channelStatus.value.find((s: any) => s.id === id)
}
function statusLabel(st?: string) {
  const map: Record<string, string> = { connected: '✅ 已连接', listening: '✅ 监听中', connecting: '⏳ 连接中...', reconnecting: '🔄 重连中...', starting: '⏳ 启动中...', stopped: '⏹ 未启动', disconnected: '⏹ 已断开' }
  if (!st) return ''
  for (const [k, v] of Object.entries(map)) if (String(st).startsWith(k)) return v
  return st
}
function channelIcon(type: string) {
  const map: Record<string, string> = { feishu: '✈️', telegram: '✈️', webhook: '🔌' }
  return map[type] || '🔌'
}
function channelTypeLabel(type: string) {
  const t = channelTypes.value.find((x: any) => x.type === type)
  return t ? t.label : type
}

onMounted(async () => {
  const [proj, bind, act, ch, types, status] = await Promise.all([
    execute('getProjects'),
    execute('getBinding'),
    execute('getActiveAgent'),
    execute('getChannels'),
    execute('getChannelTypes'),
    execute('getChannelStatus'),
  ])
  projects.value = proj || []
  for (const p of projects.value) toolSelMap.value[p.path] = 'opencode'
  const b = bind || {}
  binding.value = typeof b === 'string' ? b : (b.path || '')
  if (binding.value) toolSelMap.value[binding.value] = (typeof b === 'object' && b.tool) || 'opencode'
  activeAgent.value = act || null
  if (activeAgent.value) toolSelMap.value[activeAgent.value.path] = activeAgent.value.tool
  channels.value = ch || []
  channelTypes.value = types || []
  channelStatus.value = status || []
  startStatusPolling()
})

async function loadChannels() {
  channels.value = await execute('getChannels') || []
  channelTypes.value = await execute('getChannelTypes') || []
  channelStatus.value = await execute('getChannelStatus') || []
}

function startStatusPolling() {
  stopStatusPolling()
  statusPollTimer = setInterval(async () => {
    channelStatus.value = await execute('getChannelStatus').catch(() => []) || []
  }, 3000)
}
function stopStatusPolling() {
  if (statusPollTimer) { clearTimeout(statusPollTimer); statusPollTimer = null }
}

function openAddChannel() {
  newChannel.value = { type: 'feishu', name: '' }
  showAddModal.value = true
}

async function addChannel() {
  const id = `ch_${Date.now().toString(36)}`
  const cfg: any = { id, type: newChannel.value.type, name: newChannel.value.name || channelTypeLabel(newChannel.value.type), enabled: false, config: {} }
  if (cfg.type === 'feishu') cfg.config = { appId: '', appSecret: '' }
  else if (cfg.type === 'telegram') cfg.config = { botToken: '' }
  else if (cfg.type === 'webhook') cfg.config = { port: 8841, callbackUrl: '' }
  channels.value.push(cfg)
  showAddModal.value = false
  await execute('saveChannel', JSON.parse(JSON.stringify(cfg)))
  await loadChannels()
}

async function saveChannel(c: any) {
  await execute('saveChannel', JSON.parse(JSON.stringify(c)))
  channelStatus.value = await execute('getChannelStatus').catch(() => []) || []
}

async function toggleChannel(c: any, enabled: boolean) {
  c.enabled = enabled
  await saveChannel(c)
}

async function removeChannel(c: any) {
  if (!confirm(`删除通道「${c.name}」？`)) return
  await execute('removeChannel', { id: c.id })
  await loadChannels()
}

async function testChannel(c: any) {
  const ok = await execute('testChannel', { id: c.id })
  alert(ok ? '测试消息已发送 ✓' : '发送失败，请检查配置')
}

async function startAgent(p: any) {
  const tool = toolSelMap.value[p.path] || 'opencode'
  agentRunning.value = p.path
  agentResult.value = null
  try {
    const r = await execute('startProjectAgent', { path: p.path, tool })
    agentResult.value = r
    agentResultPath.value = p.path
    if (r?.ok && r.tool) toolSelMap.value[p.path] = r.tool
    const act = await execute('getActiveAgent')
    activeAgent.value = act || null
  } finally {
    agentRunning.value = ''
  }
}

async function stopAgent(p: any) {
  agentRunning.value = p.path
  try {
    await execute('stopProjectAgent', { path: p.path })
    activeAgent.value = null
    agentResult.value = null
  } finally {
    agentRunning.value = ''
  }
}

function isAgentActive(p: any): boolean {
  return !!activeAgent.value && activeAgent.value.path === p.path
}

async function bindFeishu(p: any) {
  const tool = toolSelMap.value[p.path] || 'opencode'
  binding.value = p.path
  await execute('bindProject', { path: p.path, tool })
}

async function removeProject(p: any) {
  await execute('removeProject', { path: p.path })
  projects.value = await execute('getProjects') || []
}

function typeIcon(type: string) {
  const map: Record<string, string> = { node: '🟢', python: '🐍', rust: '🦀', go: '🔵', dotnet: '🟣', other: '📁' }
  return map[type] || '📁'
}

async function addProjectDir() {
  const win = window as any
  let dir = ''
  if (win.mqbox?.dialog?.selectFolder) {
    dir = await win.mqbox.dialog.selectFolder()
  } else {
    dir = await execute('pickProject')
  }
  if (!dir) return
  await execute('addProject', { dir })
  projects.value = await execute('getProjects') || []
  for (const p of projects.value) if (!toolSelMap.value[p.path]) toolSelMap.value[p.path] = 'opencode'
}

async function pickAndScan() {
  const win = window as any
  let dir = ''
  if (win.mqbox?.dialog?.selectFolder) {
    dir = await win.mqbox.dialog.selectFolder()
  } else {
    dir = await execute('pickProject')
  }
  if (!dir) return
  const proj = await execute('scanCustomDir', { dir })
  if (proj) {
    projects.value = proj
    for (const p of projects.value) if (!toolSelMap.value[p.path]) toolSelMap.value[p.path] = 'opencode'
  }
}

function openFolder(path: string) {
  execute('openFolder', { path })
}

function openVSCode(path: string) {
  execute('openVSCode', { path })
}

onUnmounted(() => {
  stopStatusPolling()
})
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
.project-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.project-grid.scrollable{max-height:calc(100vh - 140px);overflow-y:auto;padding-bottom:20px}
.project-card{border:1px solid #eee;border-radius:8px;padding:12px;transition:box-shadow 0.2s}
.project-card:hover{box-shadow:0 2px 12px rgba(0,0,0,0.06)}
.card-header{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.card-type{font-size:16px}
.card-name{font-weight:600;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bound-badge{font-size:10px;color:#8B5CF6;margin-left:auto;font-weight:600}
.card-meta{display:flex;gap:12px;font-size:10px;color:#999;margin-bottom:6px}
.card-desc{font-size:11px;color:#666;margin-bottom:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card-actions{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.btn{padding:6px 12px;border:1px solid #ddd;border-radius:5px;background:#fff;color:#444;font-size:11px;cursor:pointer}
.btn:hover{background:#f5f5f5}
.btn.primary{background:#409EFF;color:#fff;border-color:#409EFF}
.btn.primary:hover{background:#66b1ff}
.btn.sm{padding:4px 8px;font-size:10px}
.tool-select{padding:3px 6px;border:1px solid #ddd;border-radius:5px;font-size:10px;background:#fff;color:#444;cursor:pointer}
.tool-select:focus{outline:none;border-color:#409EFF}
.btn.accent{background:#8B5CF6;color:#fff;border-color:#8B5CF6}
.btn.accent:hover{background:#7C3AED}
.btn.accent:disabled{opacity:.5;cursor:default}
.agent-result{border:1px solid #e0e0e0;border-radius:6px;padding:8px;margin-top:8px;background:#fafafa;font-size:11px}
.agent-result.ok{border-color:#c8e6c9;background:#f1f8f1}
.agent-result.err{border-color:#ffcdd2;background:#fff5f5}
.agent-result-head{font-weight:600;margin-bottom:4px;color:#444}
.agent-result pre{font-size:10px;white-space:pre-wrap;word-break:break-all;margin:0;color:#555;max-height:160px;overflow-y:auto}
.empty{text-align:center;padding:40px;color:#999;font-size:13px}
.settings-card{border:1px solid #eee;border-radius:8px;padding:20px;max-width:600px}
.settings-card h3{margin:0 0 16px;font-size:15px}
.card-hint{font-size:11px;color:#999;margin:4px 0 8px}
.form-row{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.form-row label{min-width:80px;font-size:12px;color:#666}
.input{flex:1;padding:7px 10px;border:1px solid #ddd;border-radius:5px;font-size:12px;outline:none}
.input:focus{border-color:#409EFF}
.channel-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
.channel-card{border:1px solid #eee;border-radius:8px;padding:14px;transition:box-shadow 0.2s}
.channel-card:hover{box-shadow:0 2px 12px rgba(0,0,0,0.06)}
.channel-state{font-size:10px;margin-left:auto;padding:2px 6px;border-radius:4px;background:#f1f5f9;color:#64748b}
.channel-state.connected,.channel-state.listening{background:#e8f5e9;color:#2e7d32}
.channel-state.connecting,.channel-state.starting,.channel-state.reconnecting{background:#fff8e1;color:#f39c12}
.channel-state.error{background:#ffebee;color:#c62828}
.channel-fields{border-top:1px dashed #eee;margin-top:10px;padding-top:10px}
.ql-mask{position:fixed;inset:0;background:rgba(15,23,42,.4);display:flex;align-items:center;justify-content:center;z-index:50}
.ql-editor{background:#fff;border-radius:12px;padding:20px 22px;width:380px;max-height:90vh;overflow-y:auto;box-shadow:0 10px 40px rgba(15,23,42,.25)}
.ql-editor h3{margin:0 0 14px;font-size:15px;color:#2c3550}
.fld{display:block;font-size:12px;color:#64748b;margin:10px 0 4px}
.inp{width:100%;border:1px solid #e2e8f0;border-radius:8px;padding:8px 10px;font-size:13px;outline:none;box-sizing:border-box}
.inp:focus{border-color:#6366f1}
.type-row{display:flex;gap:6px;flex-wrap:wrap}
.type-btn{border:1px solid #e2e8f0;background:#fff;border-radius:8px;padding:6px 10px;font-size:12px;cursor:pointer;color:#475569}
.type-btn.active{border-color:#6366f1;background:#eef2ff;color:#4f46e5}
.ed-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}
.btn.ghost{background:#f1f5f9;color:#475569}
.status-msg{padding:8px 12px;border-radius:5px;margin-top:8px;font-size:12px}
.status-msg.ok{background:#e8f5e9;color:#2e7d32}
.status-msg.err{background:#ffebee;color:#c62828}
.switch{position:relative;display:inline-block;width:36px;height:20px}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#ccc;transition:0.3s;border-radius:20px}
.slider::before{content:'';position:absolute;height:16px;width:16px;left:2px;bottom:2px;background:#fff;transition:0.3s;border-radius:50%}
.switch input:checked+.slider{background:#409EFF}
.switch input:checked+.slider::before{transform:translateX(16px)}
.btn.danger{background:#e74c3c;color:#fff;border-color:#e74c3c}
.btn.danger:hover{background:#c0392b}
</style>
